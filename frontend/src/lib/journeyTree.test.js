import test from 'node:test'
import assert from 'node:assert/strict'
import {journeyTree} from './journeyTree.js'
const chain=Array.from({length:6},(_,i)=>({id:i+1,parent_id:i||null}))
test('returning to an ancestor does not change the linear tree',()=>{
 const tree=journeyTree(chain)
 assert.equal(tree.rows.length,6)
 assert(tree.rows.every(r=>r.lane===0))
 assert.equal(tree.links.length,5)
})
test('only actual siblings split into different lanes',()=>{
 const tree=journeyTree([...chain,{id:7,parent_id:3},{id:8,parent_id:7}])
 const byId=new Map(tree.rows.map(r=>[r.visit.id,r]))
 assert.equal(byId.get(4).lane,0)
 assert.equal(byId.get(7).lane,1)
 assert.equal(byId.get(8).lane,1)
 assert.equal(tree.links.find(l=>l.id===7).parent,3)
})
test('identical articles remain distinct visits',()=>{
 const tree=journeyTree([{id:1,page_id:3,parent_id:null},{id:2,page_id:3,parent_id:1}])
 assert.equal(tree.rows.length,2)
})
test('partial pages and cyclic data do not hide visits or loop',()=>{
 assert.equal(journeyTree([{id:4,parent_id:3}]).rows.length,1)
 assert.equal(journeyTree([{id:1,parent_id:2},{id:2,parent_id:1}]).rows.length,2)
})
test('wrapped titles move subsequent nodes and keep links attached',()=>{
 const tree=journeyTree(chain,new Map([[1,92],[2,72]]))
 assert.equal(tree.rows[0].y,26)
 assert.equal(tree.rows[1].y,118)
 assert.equal(tree.rows[2].y,190)
 assert.equal(tree.height,92+72+4*52)
 assert.equal(tree.links[0].d,'M 14 26 V 118')
})
