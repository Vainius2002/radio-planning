import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'radio_planning.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Projects CRM API configuration
    PROJECTS_CRM_URL = os.environ.get('PROJECTS_CRM_URL', 'http://91.99.165.20:5002')
    PROJECTS_CRM_API_KEY = os.environ.get('PROJECTS_CRM_API_KEY', 'projects-crm-api-key-change-in-production')

    # Port configuration
    PORT = 5006
    HOST = '0.0.0.0'