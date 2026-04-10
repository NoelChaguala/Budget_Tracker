from flask import Blueprint

bp = Blueprint("main", __name__)

from . import auth, dashboard, household, transactions, budget, utils
