from flask import Blueprint

bp = Blueprint("main", __name__)

from . import auth, budget, dashboard, household, reports, transactions, utils
