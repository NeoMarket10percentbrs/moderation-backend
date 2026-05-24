from .auth.auth_router import auth_router
from .admin.admin_router import admin_router
from .queue.queue_router import queue_router
from .tickets.tickets_router import tickets_router
from .blocking_reasons.blocking_reasons_router import blocking_reasons_router
from .stats.stats_router import stats_router
from .b2b.b2b_router import b2b_router

routes = [
    auth_router,
    admin_router,
    queue_router,
    tickets_router,
    blocking_reasons_router,
    stats_router,
    b2b_router,
]
