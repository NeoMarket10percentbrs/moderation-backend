from .auth import auth_router
from .events import events_router
from .moderation import moderation_router

routes = [
    auth_router.auth_router,
    events_router.events_router,
    moderation_router.moderation_router,

]
