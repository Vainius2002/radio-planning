from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.models import db, RadioGroup, RadioStation, RadioPlan, RadioSpot, RadioClip, StationPrice, StationRating
from app.utils import fetch_campaigns_from_projects_crm, generate_time_slots
from datetime import datetime, timedelta
import json

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Main dashboard"""
    plans = RadioPlan.query.order_by(RadioPlan.created_at.desc()).limit(10).all()
    stations = RadioStation.query.all()
    groups = RadioGroup.query.all()

    return render_template('index.html',
                         plans=plans,
                         stations=stations,
                         groups=groups)

@main_bp.route('/planning')
def planning():
    """Radio planning page"""
    plans = RadioPlan.query.order_by(RadioPlan.created_at.desc()).all()
    return render_template('planning.html', plans=plans)

@main_bp.route('/planning/new')
def new_plan():
    """Create new radio plan"""
    # Fetch campaigns from projects-crm
    campaigns = fetch_campaigns_from_projects_crm()
    stations = RadioStation.query.all()
    groups = RadioGroup.query.all()

    return render_template('new_plan.html',
                         campaigns=campaigns,
                         stations=stations,
                         groups=groups)

@main_bp.route('/planning/<int:plan_id>')
def view_plan(plan_id):
    """View and edit specific radio plan"""
    from app.models import SeasonalIndex

    plan = RadioPlan.query.get_or_404(plan_id)

    # Use selected stations from the plan, fallback to all stations if none selected
    stations = plan.selected_stations if plan.selected_stations else RadioStation.query.all()

    time_slots = generate_time_slots()

    # Generate calendar data
    calendar_data = generate_calendar_data(plan)

    # Get seasonal indices for each station's group
    seasonal_indices = {}
    for station in stations:
        group_id = station.group_id
        month = plan.start_date.month  # Use plan start month

        # Try group-specific first, then global
        seasonal = SeasonalIndex.query.filter_by(month=month, group_id=group_id, is_active=True).first()
        if not seasonal:
            seasonal = SeasonalIndex.query.filter_by(month=month, group_id=None, is_active=True).first()

        seasonal_indices[station.id] = seasonal.index_value if seasonal else 1.0

    return render_template('view_plan.html',
                         plan=plan,
                         stations=stations,
                         time_slots=time_slots,
                         calendar_data=calendar_data,
                         seasonal_indices=seasonal_indices)

@main_bp.route('/planning/<int:plan_id>/calendar')
def plan_calendar(plan_id):
    """Radio plan calendar view"""
    plan = RadioPlan.query.get_or_404(plan_id)
    stations = RadioStation.query.all()
    time_slots = generate_time_slots()

    # Generate full calendar
    calendar = generate_full_calendar(plan)

    return render_template('calendar.html',
                         plan=plan,
                         stations=stations,
                         time_slots=time_slots,
                         calendar=calendar)

@main_bp.route('/stations')
def stations():
    """Manage radio stations"""
    groups = RadioGroup.query.all()
    stations = RadioStation.query.all()

    return render_template('stations.html',
                         groups=groups,
                         stations=stations)

@main_bp.route('/stations/add', methods=['POST'])
def add_station():
    """Add new radio station"""
    if request.is_json:
        # API request
        data = request.get_json()
        station_name = data['name']
        group_id = data['group_id']
    else:
        # Form request
        station_name = request.form['station_name']
        group_id = request.form['group_id']

    # Check if station already exists
    existing_station = RadioStation.query.filter_by(name=station_name).first()
    if existing_station:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Stotis jau egzistuoja'}), 400
        else:
            flash('Radijo stotis su tokiu pavadinimu jau egzistuoja!', 'error')
            return redirect(url_for('main.stations'))

    station = RadioStation(
        name=station_name,
        group_id=int(group_id)
    )
    db.session.add(station)

    # Add default prices for the new station
    time_slots = [
        "07:00-07:30", "07:30-08:00", "08:00-08:30", "08:30-09:00",
        "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00",
        "11:00-11:30", "11:30-12:00", "12:00-12:30", "12:30-13:00",
        "13:00-13:30", "13:30-14:00", "14:00-14:30", "14:30-15:00",
        "15:00-15:30", "15:30-16:00", "16:00-16:30", "16:30-17:00",
        "17:00-17:30", "17:30-18:00", "18:00-18:30", "18:30-19:00"
    ]

    db.session.flush()  # Get the station ID

    for time_slot in time_slots:
        # Base price depending on time
        hour = int(time_slot.split(':')[0])
        if 7 <= hour < 9:
            base_price = 120  # Morning prime
        elif 9 <= hour < 12:
            base_price = 80   # Morning
        elif 12 <= hour < 14:
            base_price = 100  # Lunch
        elif 14 <= hour < 17:
            base_price = 70   # Afternoon
        else:
            base_price = 110  # Evening prime

        # Weekday price
        price = StationPrice(
            station_id=station.id,
            time_slot=time_slot,
            price=base_price,
            is_weekend=False,
            is_active=True
        )
        db.session.add(price)

        # Weekend price (20% cheaper)
        weekend_price = StationPrice(
            station_id=station.id,
            time_slot=time_slot,
            price=base_price * 0.8,
            is_weekend=True,
            is_active=True
        )
        db.session.add(weekend_price)

    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'id': station.id})
    else:
        flash(f'Radijo stotis "{station_name}" sukurta sėkmingai!', 'success')
        return redirect(url_for('main.stations'))

@main_bp.route('/groups/add', methods=['POST'])
def add_group():
    """Add new radio group"""
    if request.is_json:
        data = request.get_json()
        group_name = data['name']
    else:
        group_name = request.form['group_name']

    # Check if group already exists
    existing_group = RadioGroup.query.filter_by(name=group_name).first()
    if existing_group:
        if request.is_json:
            return jsonify({'success': False, 'error': 'Grupė jau egzistuoja'}), 400
        else:
            flash('Radijo grupė su tokiu pavadinimu jau egzistuoja!', 'error')
            return redirect(url_for('main.stations'))

    group = RadioGroup(name=group_name)
    db.session.add(group)
    db.session.commit()

    if request.is_json:
        return jsonify({'success': True, 'id': group.id})
    else:
        flash(f'Radijo grupė "{group_name}" sukurta sėkmingai!', 'success')
        return redirect(url_for('main.stations'))

@main_bp.route('/stations/<int:station_id>/delete', methods=['POST'])
def delete_station(station_id):
    """Delete a radio station"""
    station = RadioStation.query.get_or_404(station_id)
    station_name = station.name

    # Delete related ratings and prices first
    StationRating.query.filter_by(station_id=station_id).delete()
    StationPrice.query.filter_by(station_id=station_id).delete()

    # Delete the station
    db.session.delete(station)
    db.session.commit()

    flash(f'Radijo stotis "{station_name}" ištrinta sėkmingai!', 'success')
    return redirect(url_for('main.stations'))

@main_bp.route('/stations/<int:station_id>/prices')
def station_prices(station_id):
    """Manage station prices and ratings"""
    station = RadioStation.query.get_or_404(station_id)
    prices = station.prices.filter_by(is_active=True).all()
    ratings = station.ratings.all()
    time_slots = generate_time_slots()

    return render_template('station_ratings.html',
                         station=station,
                         prices=prices,
                         ratings=ratings,
                         time_slots=time_slots)

@main_bp.route('/stations/<int:station_id>/ratings/update', methods=['POST'])
def update_station_ratings(station_id):
    """Update station ratings for specific time slot"""
    station = RadioStation.query.get_or_404(station_id)

    time_slot = request.form['time_slot']
    is_weekend = request.form['is_weekend'] == 'true'
    grp = float(request.form['grp'])
    trp = float(request.form['trp'])

    # Update or create rating
    rating = StationRating.query.filter_by(
        station_id=station_id,
        time_slot=time_slot,
        is_weekend=is_weekend
    ).first()

    if rating:
        rating.grp = grp
        rating.trp = trp
    else:
        rating = StationRating(
            station_id=station_id,
            time_slot=time_slot,
            grp=grp,
            trp=trp,
            is_weekend=is_weekend
        )
        db.session.add(rating)

    db.session.commit()

    period_type = "savaitgalio (Št-Sk)" if is_weekend else "darbo dienų (Pr-Pn)"
    flash(f'Stoties "{station.name}" {period_type} reitingai laiko intervale {time_slot} atnaujinti sėkmingai!', 'success')

    return redirect(url_for('main.station_prices', station_id=station_id))

@main_bp.route('/stations/<int:station_id>/pricing')
def station_pricing(station_id):
    """Manage station pricing"""
    station = RadioStation.query.get_or_404(station_id)

    # Define price zones based on Excel structure
    price_zones = [
        {'zone_letter': 'A', 'time_range': '07:00 - 10:00', 'is_weekend': False},
        {'zone_letter': 'B', 'time_range': '10:00 - 12:00', 'is_weekend': False},
        {'zone_letter': 'C', 'time_range': '12:00 - 16:00', 'is_weekend': False},
        {'zone_letter': 'B', 'time_range': '16:00 - 18:00', 'is_weekend': False},
        {'zone_letter': 'D', 'time_range': '18:00 - 07:00', 'is_weekend': False},
        {'zone_letter': 'D', 'time_range': '00:00 - 24:00 (Savaitgaliai)', 'is_weekend': True},
    ]

    # Get zone prices for this station (would need to be stored in database)
    # For now, create empty price structure
    zone_prices = {}

    # Get stored zone prices if they exist
    from app.models import StationZonePrice
    stored_prices = StationZonePrice.query.filter_by(station_id=station_id).all()
    for price in stored_prices:
        key = f"{price.zone}_{price.duration}"
        zone_prices[key] = price.price

    return render_template('station_pricing.html',
                         station=station,
                         price_zones=price_zones,
                         zone_prices=zone_prices)

@main_bp.route('/stations/<int:station_id>/price/update', methods=['POST'])
def update_station_price(station_id):
    """Update station price for specific time slot"""
    station = RadioStation.query.get_or_404(station_id)

    time_slot = request.form['time_slot']
    is_weekend = request.form['is_weekend'] == 'true'
    new_price = float(request.form['price'])

    # Find existing price or create new one
    price = StationPrice.query.filter_by(
        station_id=station_id,
        time_slot=time_slot,
        is_weekend=is_weekend,
        is_active=True
    ).first()

    if price:
        price.price = new_price
    else:
        price = StationPrice(
            station_id=station_id,
            time_slot=time_slot,
            price=new_price,
            is_weekend=is_weekend,
            is_active=True
        )
        db.session.add(price)

    db.session.commit()

    period_type = "savaitgalio (Št-Sk)" if is_weekend else "darbo dienų (Pr-Pn)"
    flash(f'Stoties "{station.name}" {period_type} kaina laiko intervale {time_slot} atnaujinta sėkmingai!', 'success')

    return redirect(url_for('main.station_pricing', station_id=station_id))

@main_bp.route('/stations/<int:station_id>/zone-price/update', methods=['POST'])
def update_zone_price(station_id):
    """Update zone-based price for station"""
    station = RadioStation.query.get_or_404(station_id)

    zone = request.form['zone']
    duration = request.form['duration']
    is_weekend = request.form['is_weekend'] == 'true'
    new_price = float(request.form['price'])

    # Find existing zone price or create new one
    from app.models import StationZonePrice
    zone_price = StationZonePrice.query.filter_by(
        station_id=station_id,
        zone=zone,
        duration=duration,
        is_weekend=is_weekend
    ).first()

    if zone_price:
        zone_price.price = new_price
    else:
        zone_price = StationZonePrice(
            station_id=station_id,
            zone=zone,
            duration=duration,
            price=new_price,
            is_weekend=is_weekend
        )
        db.session.add(zone_price)

    db.session.commit()

    flash(f'Stoties "{station.name}" zona {zone} ({duration}) kaina atnaujinta sėkmingai!', 'success')
    return redirect(url_for('main.station_pricing', station_id=station_id))

@main_bp.route('/stations/<int:station_id>/data/update', methods=['POST'])
def update_station_data(station_id):
    """Update station price and ratings for specific time slot"""
    station = RadioStation.query.get_or_404(station_id)

    time_slot = request.form['time_slot']
    is_weekend = request.form['is_weekend'] == 'true'
    new_price = float(request.form['price'])

    # Update or create price
    price = StationPrice.query.filter_by(
        station_id=station_id,
        time_slot=time_slot,
        is_weekend=is_weekend,
        is_active=True
    ).first()

    if price:
        price.price = new_price
    else:
        price = StationPrice(
            station_id=station_id,
            time_slot=time_slot,
            price=new_price,
            is_weekend=is_weekend,
            is_active=True
        )
        db.session.add(price)

    # Update or create rating if GRP and TRP provided
    if request.form.get('grp') and request.form.get('trp'):
        grp = float(request.form['grp'])
        trp = float(request.form['trp'])

        rating = StationRating.query.filter_by(
            station_id=station_id,
            time_slot=time_slot,
            is_weekend=is_weekend
        ).first()

        if rating:
            rating.grp = grp
            rating.trp = trp
        else:
            rating = StationRating(
                station_id=station_id,
                time_slot=time_slot,
                grp=grp,
                trp=trp,
                is_weekend=is_weekend
            )
            db.session.add(rating)

    db.session.commit()

    period_type = "savaitgalio (Št-Sk)" if is_weekend else "darbo dienų (Pr-Pn)"
    flash(f'Stoties "{station.name}" {period_type} duomenys laiko intervale {time_slot} atnaujinti sėkmingai!', 'success')

    return redirect(url_for('main.station_prices', station_id=station_id))

@main_bp.route('/groups/<int:group_id>/seasonal-adjustments')
def group_seasonal_adjustments(group_id):
    """Group-specific seasonal adjustments management page"""
    from app.models import RadioGroup, SeasonalIndex

    group = RadioGroup.query.get_or_404(group_id)
    indices = SeasonalIndex.query.filter_by(group_id=group_id, is_active=True).order_by('month').all()

    # If no group-specific indices exist, create default ones
    if not indices:
        months = [
            (1, 'Sausis'), (2, 'Vasaris'), (3, 'Kovas'), (4, 'Balandis'),
            (5, 'Gegužė'), (6, 'Birželis'), (7, 'Liepa'), (8, 'Rugpjūtis'),
            (9, 'Rugsėjis'), (10, 'Spalis'), (11, 'Lapkritis'), (12, 'Gruodis')
        ]

        for month, name in months:
            index = SeasonalIndex(
                month=month,
                name=name,
                index_value=1.0,
                group_id=group_id,
                is_active=True
            )
            db.session.add(index)

        db.session.commit()
        indices = SeasonalIndex.query.filter_by(group_id=group_id, is_active=True).order_by('month').all()

    return render_template('group_seasonal_adjustments.html', group=group, indices=indices)


@main_bp.route('/debug/data')
def debug_data():
    """Debug route to show all imported data"""
    groups = RadioGroup.query.all()
    stations = RadioStation.query.all()
    ratings = StationRating.query.limit(20).all()
    prices = StationPrice.query.limit(20).all()

    debug_info = {
        'groups_count': len(groups),
        'stations_count': len(stations),
        'ratings_count': StationRating.query.count(),
        'prices_count': StationPrice.query.count(),
        'groups': [(g.name, len(g.stations.all())) for g in groups],
        'sample_stations': [(s.name, s.group.name) for s in stations[:10]],
        'sample_ratings': [(r.station.name, r.time_slot, r.grp, r.trp, r.is_weekend) for r in ratings],
        'sample_prices': [(p.station.name, p.time_slot, p.price, p.is_weekend) for p in prices]
    }

    return jsonify(debug_info)

def generate_calendar_data(plan):
    """Generate calendar data structure for the plan"""
    from datetime import timedelta

    calendar_data = {
        'dates': [],
        'spots': {}
    }

    # Generate list of dates for the template
    current_date = plan.start_date
    while current_date <= plan.end_date:
        calendar_data['dates'].append(current_date)
        current_date += timedelta(days=1)

    # Fill with spots
    for spot in plan.spots:
        date_key = spot.date.isoformat()
        slot_key = f"{spot.station_id}_{spot.time_slot}"

        if slot_key not in calendar_data['spots']:
            calendar_data['spots'][slot_key] = {}

        calendar_data['spots'][slot_key][date_key] = {
            'station': spot.station.name,
            'count': spot.spot_count,
            'clip': spot.clip.name if spot.clip else '',
            'price': spot.final_price
        }

    return calendar_data

def generate_full_calendar(plan):
    """Generate full calendar with all metrics"""
    calendar = {
        'dates': [],
        'time_slots': {},
        'totals': {
            'grp': 0,
            'trp': 0,
            'price': 0,
            'spots': 0
        }
    }

    # Generate dates
    current_date = plan.start_date
    while current_date <= plan.end_date:
        calendar['dates'].append({
            'date': current_date,
            'weekday': current_date.strftime('%A'),
            'is_weekend': current_date.weekday() >= 5
        })
        current_date += timedelta(days=1)

    # Generate time slots with spots
    for slot in generate_time_slots():
        calendar['time_slots'][slot] = {
            'spots': {},
            'total_grp': 0,
            'total_trp': 0,
            'total_price': 0
        }

        # Get spots for this time slot
        spots = plan.spots.filter_by(time_slot=slot).all()

        for spot in spots:
            date_key = spot.date.isoformat()
            if date_key not in calendar['time_slots'][slot]['spots']:
                calendar['time_slots'][slot]['spots'][date_key] = []

            calendar['time_slots'][slot]['spots'][date_key].append({
                'station': spot.station.name,
                'count': spot.spot_count,
                'grp': spot.grp,
                'trp': spot.trp,
                'price': spot.final_price
            })

            # Update totals
            calendar['time_slots'][slot]['total_grp'] += spot.grp
            calendar['time_slots'][slot]['total_trp'] += spot.trp
            calendar['time_slots'][slot]['total_price'] += spot.final_price

            calendar['totals']['grp'] += spot.grp
            calendar['totals']['trp'] += spot.trp
            calendar['totals']['price'] += spot.final_price
            calendar['totals']['spots'] += spot.spot_count

    # Remove empty time slots
    empty_slots = []
    for slot, data in calendar['time_slots'].items():
        if not data['spots']:
            empty_slots.append(slot)

    for slot in empty_slots:
        del calendar['time_slots'][slot]

    return calendar