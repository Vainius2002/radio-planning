from flask import Blueprint, jsonify, request, send_file, current_app
from app.models import db, RadioGroup, RadioStation, StationPrice, StationRating, RadioPlan, RadioSpot, RadioClip, SeasonalIndex
from app.utils import fetch_campaigns_from_projects_crm, import_station_prices, import_station_ratings, export_plan_to_excel
from datetime import datetime
import os

api_bp = Blueprint('api', __name__)

@api_bp.route('/campaigns', methods=['GET'])
def get_campaigns():
    """Fetch campaigns from projects-crm"""
    campaigns = fetch_campaigns_from_projects_crm()
    return jsonify(campaigns)

@api_bp.route('/radio-groups', methods=['GET'])
def get_radio_groups():
    """Get all radio groups with their stations"""
    groups = RadioGroup.query.all()
    result = []
    for group in groups:
        group_data = {
            'id': group.id,
            'name': group.name,
            'stations': [
                {
                    'id': s.id,
                    'name': s.name
                } for s in group.stations
            ]
        }
        result.append(group_data)
    return jsonify(result)

@api_bp.route('/radio-stations', methods=['GET'])
def get_radio_stations():
    """Get all radio stations"""
    stations = RadioStation.query.all()
    result = []
    for station in stations:
        station_data = {
            'id': station.id,
            'name': station.name,
            'group_id': station.group_id,
            'group_name': station.group.name
        }
        result.append(station_data)
    return jsonify(result)

@api_bp.route('/radio-stations/<int:station_id>/prices', methods=['GET'])
def get_station_prices(station_id):
    """Get prices for a specific station"""
    station = RadioStation.query.get_or_404(station_id)
    prices = station.prices.filter_by(is_active=True).all()
    result = []
    for price in prices:
        result.append({
            'id': price.id,
            'time_slot': price.time_slot,
            'price': price.price,
            'is_weekend': price.is_weekend
        })
    return jsonify(result)

@api_bp.route('/radio-stations/<int:station_id>/ratings', methods=['GET'])
def get_station_ratings(station_id):
    """Get ratings for a specific station"""
    station = RadioStation.query.get_or_404(station_id)
    target_audience = request.args.get('target_audience', 'All')

    ratings = station.ratings.filter_by(
        target_audience=target_audience,
        is_active=True
    ).all()

    result = []
    for rating in ratings:
        result.append({
            'id': rating.id,
            'time_slot': rating.time_slot,
            'grp': rating.grp,
            'trp': rating.trp,
            'affinity': rating.affinity,
            'is_weekend': rating.is_weekend
        })
    return jsonify(result)

@api_bp.route('/import-prices', methods=['POST'])
def import_prices():
    """Import prices from Excel file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.xlsx'):
        # Save temporarily
        temp_path = os.path.join('/tmp', file.filename)
        file.save(temp_path)

        # Import
        success, message = import_station_prices(temp_path)

        # Clean up
        os.remove(temp_path)

        if success:
            return jsonify({'message': message}), 200
        else:
            return jsonify({'error': message}), 500

    return jsonify({'error': 'Invalid file format'}), 400

@api_bp.route('/import-ratings', methods=['POST'])
def import_ratings():
    """Import ratings from Excel file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.xlsx'):
        # Save temporarily
        temp_path = os.path.join('/tmp', file.filename)
        file.save(temp_path)

        # Import
        success, message = import_station_ratings(temp_path)

        # Clean up
        os.remove(temp_path)

        if success:
            return jsonify({'message': message}), 200
        else:
            return jsonify({'error': message}), 500

    return jsonify({'error': 'Invalid file format'}), 400

@api_bp.route('/plans', methods=['POST'])
def create_plan():
    """Create a new radio plan"""
    try:
        data = request.json
        print(f"=== CREATE PLAN API CALLED ===")
        print(f"Received data: {data}")

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        required_fields = ['campaign_id', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        plan = RadioPlan(
            campaign_id=data['campaign_id'],
            campaign_name=data.get('campaign_name'),
            project_id=data.get('project_id'),
            project_name=data.get('project_name'),
            client_brand_id=data.get('client_brand_id'),
            client_brand_name=data.get('client_brand_name'),
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            target_audience=data.get('target_audience', 'All'),
            our_discount=data.get('our_discount', 0),
            client_discount=data.get('client_discount', 0)
        )

        db.session.add(plan)
        db.session.flush()  # Get the plan ID
        print(f"Plan created with ID: {plan.id}")

        # Add selected stations
        for station_data in data.get('stations', []):
            station = RadioStation.query.get(station_data['id'])
            if station:
                plan.selected_stations.append(station)
                print(f"Added station: {station_data['name']}")

        # Add clips
        for clip_data in data.get('clips', []):
            clip = RadioClip(
                plan_id=plan.id,
                name=clip_data['name'],
                duration=clip_data['duration']
            )
            db.session.add(clip)
            print(f"Added clip: {clip_data['name']}")

        # Flush to ensure plan has its relationships loaded
        db.session.flush()

        # Capture current station data for this plan
        from app.utils import capture_station_data_for_plan
        capture_station_data_for_plan(plan)

        db.session.commit()
        print(f"Plan {plan.id} committed successfully with captured station data")

        return jsonify({'id': plan.id, 'message': 'Plan created successfully'}), 201

    except Exception as e:
        print(f"ERROR creating plan: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'Error creating plan: {str(e)}'}), 500

@api_bp.route('/plans/<int:plan_id>', methods=['GET'])
def get_plan(plan_id):
    """Get a specific plan"""
    plan = RadioPlan.query.get_or_404(plan_id)

    result = {
        'id': plan.id,
        'campaign_id': plan.campaign_id,
        'campaign_name': plan.campaign_name,
        'project_name': plan.project_name,
        'client_brand_name': plan.client_brand_name,
        'start_date': plan.start_date.isoformat(),
        'end_date': plan.end_date.isoformat(),
        'target_audience': plan.target_audience,
        'our_discount': plan.our_discount,
        'client_discount': plan.client_discount,
        'clips': [
            {
                'id': clip.id,
                'name': clip.name,
                'duration': clip.duration
            } for clip in plan.clips
        ],
        'spots': [
            {
                'id': spot.id,
                'station_id': spot.station_id,
                'station_name': spot.station.name,
                'date': spot.date.isoformat(),
                'time_slot': spot.time_slot,
                'spot_count': spot.spot_count,
                'grp': spot.grp,
                'trp': spot.trp,
                'final_price': spot.final_price
            } for spot in plan.spots
        ]
    }

    return jsonify(result)

@api_bp.route('/plans/<int:plan_id>/captured-data', methods=['GET'])
def get_plan_captured_data(plan_id):
    """Get captured station data for a plan"""
    plan = RadioPlan.query.get_or_404(plan_id)

    captured_data = plan.captured_station_data
    result = []

    for data in captured_data:
        result.append({
            'station_id': data.station_id,
            'station_name': data.station.name,
            'time_slot': data.time_slot,
            'is_weekend': data.is_weekend,
            'grp': data.grp,
            'trp': data.trp,
            'affinity': data.affinity,
            'base_price': data.base_price,
            'seasonal_index': data.seasonal_index
        })

    return jsonify(result)

@api_bp.route('/plans/<int:plan_id>/spots', methods=['POST'])
def add_spot():
    """Add a spot to a plan"""
    plan_id = request.view_args['plan_id']
    plan = RadioPlan.query.get_or_404(plan_id)
    data = request.json

    spot = RadioSpot(
        plan_id=plan_id,
        station_id=data['station_id'],
        clip_id=data.get('clip_id'),
        date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        time_slot=data['time_slot'],
        spot_count=data.get('spot_count', 1),
        clip_duration=data.get('clip_duration', 30)
    )

    # Calculate weekday
    spot.weekday = spot.date.strftime('%A')

    # Calculate metrics
    from app.utils import calculate_spot_metrics
    calculate_spot_metrics(spot, plan)

    db.session.add(spot)
    db.session.commit()

    return jsonify({'id': spot.id, 'message': 'Spot added successfully'}), 201

@api_bp.route('/plans/<int:plan_id>/export', methods=['GET'])
def export_plan(plan_id):
    """Export plan to Excel"""
    plan = RadioPlan.query.get_or_404(plan_id)
    output = export_plan_to_excel(plan)

    filename = f"radio_plan_{plan.campaign_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@api_bp.route('/seasonal-indices', methods=['GET'])
def get_seasonal_indices():
    """Get seasonal indices"""
    indices = SeasonalIndex.query.filter_by(is_active=True).order_by('month').all()
    result = []
    for index in indices:
        result.append({
            'id': index.id,
            'month': index.month,
            'name': index.name,
            'index_value': index.index_value
        })
    return jsonify(result)

@api_bp.route('/seasonal-indices/<int:index_id>', methods=['PUT'])
def update_seasonal_index(index_id):
    """Update a seasonal index"""
    index = SeasonalIndex.query.get_or_404(index_id)
    data = request.json

    index.index_value = data.get('index_value', index.index_value)
    db.session.commit()

    return jsonify({'message': 'Index updated successfully'}), 200

@api_bp.route('/radio-stations/<int:station_id>/price', methods=['GET'])
def get_station_price_for_duration(station_id):
    """Get price for specific station, time slot, duration and weekend"""
    station = RadioStation.query.get_or_404(station_id)

    # Get query parameters
    time_slot = request.args.get('time_slot')
    duration = request.args.get('duration', '30')  # default 30s
    is_weekend = request.args.get('is_weekend', 'false').lower() == 'true'

    if not time_slot:
        return jsonify({'error': 'time_slot parameter required'}), 400

    # Map time slots to zones based on hour ranges
    def get_zone_for_time_slot(time_slot, is_weekend):
        # Extract start hour from time_slot like "07:00-07:30"
        start_time = time_slot.split('-')[0]
        hour = int(start_time.split(':')[0])

        # Time zone mapping:
        # A: 07:00 - 10:00
        # B: 10:00 - 12:00
        # C: 12:00 - 16:00
        # B: 16:00 - 18:00
        # D: 18:00 - 07:00 (and all other hours)
        # D: 00:00 - 24:00 (Weekends - all day)

        if is_weekend:
            return 'D'  # All weekend hours are Zone D
        elif 7 <= hour < 10:
            return 'A'
        elif 10 <= hour < 12:
            return 'B'
        elif 12 <= hour < 16:
            return 'C'
        elif 16 <= hour < 18:
            return 'B'
        else:
            return 'D'  # 18:00-07:00 and other hours

    # Get the zone for this time slot
    zone = get_zone_for_time_slot(time_slot, is_weekend)

    # Find StationZonePrice for this zone and duration
    from app.models import StationZonePrice

    # Get all zone prices for this station, zone, and weekend status
    zone_prices = StationZonePrice.query.filter_by(
        station_id=station_id,
        zone=zone,
        is_weekend=is_weekend
    ).all()

    # Convert duration strings to integers and find the best match (closest duration >= clip duration)
    clip_duration_int = int(duration)
    best_zone_price = None

    for zp in zone_prices:
        # Extract duration number from string like "60s"
        zp_duration = int(zp.duration.replace('s', ''))

        # Find the smallest duration that is >= clip duration
        if zp_duration >= clip_duration_int:
            if best_zone_price is None or zp_duration < int(best_zone_price.duration.replace('s', '')):
                best_zone_price = zp

    if best_zone_price:
        return jsonify({
            'price': best_zone_price.price,
            'duration': duration,
            'matched_duration': best_zone_price.duration,
            'zone': zone,
            'source': 'zone_price'
        })

    # Fallback to StationPrice if no zone price found
    station_price = station.prices.filter_by(
        time_slot=time_slot,
        is_weekend=is_weekend,
        is_active=True
    ).first()

    if station_price:
        return jsonify({
            'price': station_price.price,
            'duration': duration,
            'source': 'station_price_fallback'
        })

    return jsonify({'price': 0, 'duration': duration, 'source': 'not_found'})


@api_bp.route('/stations/<int:station_id>/ratings', methods=['PUT'])
def update_station_rating(station_id):
    """Update station rating (GRP/TRP) for specific time slot"""
    try:
        station = RadioStation.query.get_or_404(station_id)
        data = request.json

        time_slot = data.get('time_slot')
        is_weekend = data.get('is_weekend', False)
        grp = float(data.get('grp', 0))
        trp = float(data.get('trp', 0))

        if not time_slot:
            return jsonify({'error': 'Time slot is required'}), 400

        # Find existing rating or create new one
        rating = StationRating.query.filter_by(
            station_id=station_id,
            time_slot=time_slot,
            is_weekend=is_weekend
        ).first()

        if rating:
            # Update existing rating
            rating.grp = grp
            rating.trp = trp
            rating.is_active = True
        else:
            # Create new rating
            rating = StationRating(
                station_id=station_id,
                time_slot=time_slot,
                grp=grp,
                trp=trp,
                is_weekend=is_weekend,
                is_active=True
            )
            db.session.add(rating)

        db.session.commit()

        return jsonify({
            'success': True,
            'rating': {
                'id': rating.id,
                'time_slot': rating.time_slot,
                'grp': rating.grp,
                'trp': rating.trp,
                'is_weekend': rating.is_weekend
            }
        })

    except ValueError as e:
        return jsonify({'error': 'Invalid number format'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Error updating rating: {str(e)}'}), 500