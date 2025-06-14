AI-Agent Buyer Assistant

Overview

This is a Django-based web application with support for GraphQL (via Graphene-Django), REST APIs (via Django REST Framework), and asynchronous task processing (via Celery). The project uses Redis as a message broker for Celery and includes JWT authentication, filtering, and other utilities for building a robust backend.

Prerequisites

Python: 3.12.10
Pipenv: For dependency management
Redis: For Celery task queue (download from redis.io or use a package manager)
Git: For version control
Setup Instructions

1. Clone the Repository

If the project is version-controlled, clone it:

git clone <repository-url>
cd testt

2. Set Up the Virtual Environment

Install dependencies using Pipenv:

pipenv install

Activate the virtual environment:

pipenv shell

3. Configure Environment Variables

Create a .env file in the project root (C:\Users\fedir\Documents\testt) and add necessary configurations, e.g.:

DEBUG=True
SECRET_KEY=your-secret-key
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

4. Install Redis

Ensure Redis is installed and running:





On Windows, download and install Redis or use WSL2.



Start Redis:

redis-server

5. Apply Migrations

Run database migrations:

python manage.py migrate

6. Start the Django Development Server

Run the Django server:

python manage.py runserver

Access the application at http://localhost:8000.

7. Start the Celery Worker

For asynchronous tasks, start the Celery worker with the gevent pool (recommended for Windows):

pipenv run celery -A checkout_agent worker -l info -P gevent

Alternatively, use the solo pool for simplicity:

pipenv run celery -A checkout_agent worker -l info -P solo

Project Structure





manage.py: Django’s command-line utility.



checkout_agent/: Contains Celery configuration (e.g., celery.py).



Pipfile and Pipfile.lock: Dependency management files.



Apps: Application-specific code (e.g., models, views, GraphQL schemas).

Key Dependencies





Django: 5.2.1



djangorestframework: 3.16.0



django-graphql-jwt: For GraphQL JWT authentication



django-filter: For filtering querysets



graphene-django: For GraphQL API



celery: 5.5.3 (with Redis as broker)



gevent: For asynchronous task processing



django-tailwind: For Tailwind CSS integration

Run pipenv run pip list to see all installed packages.

Usage





REST API: Access REST endpoints via http://localhost:8000/api/ (configure as needed).



GraphQL API: Access the GraphQL endpoint at http://localhost:8000/graphql/ (if configured).



Celery Tasks: Define tasks in your app’s tasks.py and trigger them via Celery.

Development





Add Dependencies:

pipenv install <package-name>



Run Tests:

python manage.py test



Debugging: Set DEBUG=True in .env for development.
