"""Create the single course-local UI administrator on first startup."""
from superset.app import create_app
app = create_app()
with app.app_context():
    manager = app.appbuilder.sm
    if manager.find_user(username='course_admin') is None:
        manager.add_user('course_admin', 'Course', 'Reviewer', 'course@example.invalid',
                         manager.find_role('Admin'), 'course_local_only')
