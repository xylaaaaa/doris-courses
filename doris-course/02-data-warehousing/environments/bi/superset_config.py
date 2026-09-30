"""Loopback-only teaching environment, not a production deployment."""
SECRET_KEY = 'course-superset-local-only-not-for-production-20260930'
SQLALCHEMY_DATABASE_URI = 'sqlite:////app/superset_home/course.db'
FEATURE_FLAGS = {'ENABLE_TEMPLATE_PROCESSING': False}
WTF_CSRF_ENABLED = True
TALISMAN_ENABLED = False
ENABLE_PROXY_FIX = False
