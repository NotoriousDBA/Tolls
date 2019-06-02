from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for
)
from werkzeug.exceptions import abort

from webtoll.db import get_db

from datetime import datetime
from datetime import timedelta

import json

bp = Blueprint('gettolldata', __name__)

@bp.route('/gettollprices/<int:ramp_on>/<int:ramp_off>/<int:minutes>')
def get_toll_prices(ramp_on, ramp_off, minutes):
    db = get_db()

    args = {'ramp_on':ramp_on, 'ramp_off':ramp_off}
    args['min_date'] = datetime.now() - timedelta(minutes=minutes)

    try:
        curs = db.cursor(dictionary=True)

        curs.execute('''
            SELECT DATE_FORMAT(toll_start_date, '%Y%m%d%H%i') toll_start_date,
                DATE_FORMAT(toll_end_date, '%Y%m%d%H%i') toll_end_date,
                CONVERT(COALESCE(price_495, 0) + COALESCE(price_95, 0), CHAR) toll_price
              FROM toll_log
              WHERE ramp_on = %(ramp_on)s
                AND ramp_off = %(ramp_off)s
                AND toll_end_date >= %(min_date)s
              ORDER BY toll_end_date DESC, toll_start_date DESC
        ''', args)

        data = curs.fetchall()
    finally:
        curs.close()

    return json.dumps(data)
