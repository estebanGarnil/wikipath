import atexit
from threading import Lock

from django.conf import settings
from neo4j import GraphDatabase, Query, RoutingControl


_driver = None
_driver_lock = Lock()


def get_driver():
    global _driver

    with _driver_lock:
        if _driver is None:
            _driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(
                    settings.NEO4J_USER,
                    settings.NEO4J_PASSWORD,
                ),
                connection_timeout=5,
                connection_acquisition_timeout=10,
                max_connection_pool_size=10,
                max_transaction_retry_time=5,
            )

    return _driver


def close_driver():
    global _driver

    with _driver_lock:
        if _driver is not None:
            _driver.close()
            _driver = None


def read_query(cypher, parameters=None, timeout=5):
    records, _, _ = get_driver().execute_query(
        Query(cypher, timeout=timeout),
        parameters_=parameters or {},
        database_=settings.NEO4J_DATABASE,
        routing_=RoutingControl.READ,
    )
    return [record.data() for record in records]


atexit.register(close_driver)