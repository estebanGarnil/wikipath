import test from 'node:test'
import assert from 'node:assert/strict'
import {ancestorPath,branchGraph} from './branchGraph.js'
const visits=Array.from({length:7},(_,i)=>({id:i+1,page_id:i+1,title:String(i+1),parent_id:i||null}))
const cache=Object.fromEntries(visits.map(v=>[`${v.page_id}:out`,{nodes:[v,{page_id:v.page_id+100,title:'Neighbor'}],edges:[{source:v.page_id,target:v.page_id+100,type:'LINKS_TO'}]}]))
test('F shows C D E F; G evicts C',()=>{
 const f=branchGraph(ancestorPath(visits,6),cache)
 assert.deepEqual(f.nodes.filter(n=>n.page_id<100).map(n=>n.page_id),[3,4,5,6])
 assert(!f.nodes.some(n=>n.page_id===102))
 assert(!branchGraph(ancestorPath(visits,7),cache).nodes.some(n=>n.page_id===3||n.page_id===103))
})
test('return to C restores A B C',()=>{
 const g=branchGraph(ancestorPath(visits,3),cache)
 assert.deepEqual(g.nodes.filter(n=>n.page_id<100).map(n=>n.page_id),[1,2,3])
 assert.deepEqual([...g.navigable],[103])
})
test('fork preserves original branch and supports repeated pages',()=>{
 const fork=[...visits,{id:8,page_id:90,parent_id:3},{id:9,page_id:1,parent_id:8}]
 assert.deepEqual(ancestorPath(fork,8).map(v=>v.id),[1,2,3,8])
 assert.deepEqual(ancestorPath(fork,6).map(v=>v.id),[1,2,3,4,5,6])
 assert.deepEqual(ancestorPath(fork,9).map(v=>v.id),[1,2,3,8,9])
})
test('200 node budget prioritizes current neighbors',()=>{
 const large={}
 for(const v of visits) large[`${v.page_id}:out`]={nodes:Array.from({length:80},(_,i)=>({page_id:v.page_id*1000+i,title:'n'})),edges:Array.from({length:80},(_,i)=>({source:v.page_id,target:v.page_id*1000+i,type:'LINKS_TO'}))}
 const g=branchGraph(ancestorPath(visits,7),large)
 assert.equal(g.nodes.length,200);assert.equal(g.navigable.size,80)
 const ids=new Set(g.nodes.map(n=>n.page_id))
 assert(g.edges.every(e=>ids.has(e.source)&&ids.has(e.target)))
})
test('empty graph and cyclic data terminate',()=>{
 assert.equal(branchGraph([],{}).nodes.length,0)
 assert.equal(ancestorPath([{id:1,parent_id:2},{id:2,parent_id:1}],1).length,2)
})
