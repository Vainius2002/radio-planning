import pandas as pd
import os
from datetime import datetime, time
from app.models import db, RadioGroup, RadioStation, StationPrice, StationRating, SeasonalIndex

def initialize_default_data():
    """Initialize default radio groups and seasonal indices"""
    # Check if data already exists
    if RadioGroup.query.first():
        return

    # Create radio groups
    groups_data = [
        {'name': 'Tango'},
        {'name': 'Reklamos ekspertai'},
        {'name': 'PHR'}
    ]

    for group_data in groups_data:
        group = RadioGroup(**group_data)
        db.session.add(group)

    # Create default seasonal indices (all 1.0 for now)
    for month in range(1, 13):
        index = SeasonalIndex(
            name=f'Month {month}',
            month=month,
            index_value=1.0,
            is_active=True
        )
        db.session.add(index)

    db.session.commit()

def import_station_prices(excel_file):
    """Import station prices from Excel file"""
    try:
        # Read Excel file - looking for 2025 prices
        df = pd.read_excel(excel_file, sheet_name=None)

        # Process each sheet (assume each sheet is a station or time period)
        for sheet_name, data in df.items():
            if '2025' in sheet_name or data.columns.str.contains('2025').any():
                process_price_data(data)

        db.session.commit()
        return True, "Prices imported successfully"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def import_station_ratings(excel_file):
    """Import station ratings (GRP/TRP) from Excel file"""
    try:
        df = pd.read_excel(excel_file, sheet_name=None)

        for sheet_name, data in df.items():
            process_rating_data(data)

        db.session.commit()
        return True, "Ratings imported successfully"
    except Exception as e:
        db.session.rollback()
        return False, str(e)

def process_price_data(df):
    """Process price data from DataFrame"""
    # This will be customized based on actual Excel structure
    # For now, creating a basic structure
    for _, row in df.iterrows():
        if pd.notna(row.get('Station')) and pd.notna(row.get('Price')):
            # Find or create station
            station_name = str(row['Station'])
            station = RadioStation.query.filter_by(name=station_name).first()

            if not station:
                # Assign to a default group for now
                default_group = RadioGroup.query.first()
                station = RadioStation(name=station_name, group_id=default_group.id)
                db.session.add(station)
                db.session.flush()

            # Add price
            time_slot = row.get('Time', '07:00-08:00')
            is_weekend = row.get('Weekend', False)

            price = StationPrice(
                station_id=station.id,
                time_slot=time_slot,
                price=float(row['Price']),
                is_weekend=bool(is_weekend),
                is_active=True
            )
            db.session.add(price)

def process_rating_data(df):
    """Process rating data from DataFrame"""
    for _, row in df.iterrows():
        if pd.notna(row.get('Station')):
            station_name = str(row['Station'])
            station = RadioStation.query.filter_by(name=station_name).first()

            if station:
                rating = StationRating(
                    station_id=station.id,
                    time_slot=row.get('Time', '07:00-08:00'),
                    target_audience=row.get('Audience', 'All'),
                    grp=float(row.get('GRP', 0)),
                    trp=float(row.get('TRP', 0)),
                    is_weekend=bool(row.get('Weekend', False)),
                    is_active=True
                )
                db.session.add(rating)

def generate_time_slots():
    """Generate time slots from 7:00 to 20:00"""
    slots = []
    for hour in range(7, 20):
        slot = f"{hour:02d}:00-{hour:02d}:30"
        slots.append(slot)
        if hour < 19:  # Don't create 19:30-20:00 twice
            slot = f"{hour:02d}:30-{hour+1:02d}:00"
            slots.append(slot)
        elif hour == 19:
            slot = "19:30-20:00"
            slots.append(slot)
    return slots

def fetch_campaigns_from_projects_crm():
    """Fetch campaigns from projects-crm API"""
    import requests
    from flask import current_app

    try:
        url = f"{current_app.config['PROJECTS_CRM_URL']}/api/campaigns"
        headers = {
            'X-API-Key': current_app.config['PROJECTS_CRM_API_KEY'],
            'Content-Type': 'application/json'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            return []
    except Exception as e:
        print(f"Error fetching campaigns: {e}")
        return []

def calculate_spot_metrics(spot, plan):
    """Calculate metrics for a radio spot"""
    # Get ratings for the spot
    is_weekend = spot.date.weekday() >= 5
    rating = StationRating.query.filter_by(
        station_id=spot.station_id,
        time_slot=spot.time_slot,
        target_audience=plan.target_audience,
        is_weekend=is_weekend,
        is_active=True
    ).first()

    if rating:
        spot.grp = rating.grp * spot.spot_count
        spot.trp = rating.trp * spot.spot_count
        spot.affinity = rating.affinity

    # Calculate price
    spot.calculate_price(plan.our_discount, plan.client_discount)

    return spot

def export_plan_to_excel(plan):
    """Export radio plan to Excel file"""
    import xlsxwriter
    from io import BytesIO

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Radio Plan')

    # Add formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D9E1F2',
        'border': 1
    })

    date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
    money_format = workbook.add_format({'num_format': '€#,##0.00'})
    percent_format = workbook.add_format({'num_format': '0.0%'})

    # Write headers
    headers = [
        'Kanalas', 'Laikas', 'Savaitės diena', 'Spec. pozicija',
        'Klipų skaičius', 'Klipo trukmė', 'GRP', 'TRP',
        'Viso GRP', 'Viso TRP', 'Affinity', '1 sec TRP kaina',
        'Įkainis', 'Antkainis', 'Antkainis padidintas',
        'Klipo kaina EUR', 'Kaina po nuolaidos EUR',
        'Viso kaina iki nuolaidos', 'Viso kaina po nuolaidos',
        'Nuolaida %'
    ]

    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Add calendar header (dates)
    start_col = len(headers)
    current_date = plan.start_date
    date_cols = {}

    while current_date <= plan.end_date:
        worksheet.write(0, start_col, current_date.strftime('%d/%m'), header_format)
        date_cols[current_date] = start_col
        start_col += 1
        current_date = current_date + pd.Timedelta(days=1)

    # Write spot data
    spots = plan.spots.order_by('date', 'time_slot').all()
    row = 1

    time_slot_rows = {}
    for spot in spots:
        key = (spot.station_id, spot.time_slot)
        if key not in time_slot_rows:
            time_slot_rows[key] = row

            # Write row data
            worksheet.write(row, 0, spot.station.name)
            worksheet.write(row, 1, spot.time_slot)
            worksheet.write(row, 2, spot.weekday)
            worksheet.write(row, 3, spot.special_position or '')
            worksheet.write(row, 4, spot.spot_count)
            worksheet.write(row, 5, spot.clip_duration)
            worksheet.write(row, 6, spot.grp)
            worksheet.write(row, 7, spot.trp)
            worksheet.write(row, 8, spot.grp * spot.spot_count)
            worksheet.write(row, 9, spot.trp * spot.spot_count)
            worksheet.write(row, 10, spot.affinity, percent_format)
            worksheet.write(row, 11, spot.price_per_trp, money_format)
            worksheet.write(row, 12, spot.base_price, money_format)
            worksheet.write(row, 13, spot.seasonal_index, percent_format)
            worksheet.write(row, 14, spot.price_with_index, money_format)
            worksheet.write(row, 15, spot.base_price, money_format)
            worksheet.write(row, 16, spot.final_price, money_format)
            worksheet.write(row, 17, spot.base_price * spot.spot_count, money_format)
            worksheet.write(row, 18, spot.final_price * spot.spot_count, money_format)

            total_discount = 1 - (spot.final_price / spot.base_price) if spot.base_price > 0 else 0
            worksheet.write(row, 19, total_discount, percent_format)

            row += 1

        # Mark spot in calendar
        if spot.date in date_cols:
            worksheet.write(
                time_slot_rows[key],
                date_cols[spot.date],
                spot.spot_count
            )

    # Auto-fit columns
    worksheet.set_column(0, 0, 20)  # Station name
    worksheet.set_column(1, 1, 12)  # Time
    worksheet.set_column(2, 19, 10)  # Other columns

    workbook.close()
    output.seek(0)

    return output

def capture_station_data_for_plan(plan):
    """Capture current station ratings and prices when plan is created"""
    from app.models import PlanStationData, StationRating, StationZonePrice, SeasonalIndex

    print(f"Capturing station data for plan {plan.id}")

    # Get all time slots
    time_slots = generate_time_slots()

    # For each selected station, capture data for all time slots
    for station in plan.selected_stations:
        print(f"Capturing data for station {station.name} (ID: {station.id})")

        # Get all months within the plan's date range
        start_month = plan.start_date.month
        end_month = plan.end_date.month
        start_year = plan.start_date.year
        end_year = plan.end_date.year

        # Generate list of months within the plan's date range
        months_in_plan = []
        current_date = plan.start_date.replace(day=1)  # Start from first day of start month
        while current_date <= plan.end_date:
            months_in_plan.append(current_date.month)
            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        print(f"Plan covers months: {months_in_plan}")

        # Capture data for each month, time slot, and weekend combination
        for month in months_in_plan:
            # Get seasonal index for this station and month
            seasonal_index = 1.0
            seasonal = SeasonalIndex.query.filter_by(
                group_id=station.group_id,
                month=month,
                is_active=True
            ).first()
            if not seasonal:
                # Fall back to global seasonal index for this month
                seasonal = SeasonalIndex.query.filter_by(
                    group_id=None,
                    month=month,
                    is_active=True
                ).first()
            if seasonal:
                seasonal_index = seasonal.index_value

            print(f"Month {month}: Seasonal index = {seasonal_index}")

            for time_slot in time_slots:
                for is_weekend in [False, True]:
                    # Get current ratings
                    rating = StationRating.query.filter_by(
                        station_id=station.id,
                        time_slot=time_slot,
                        target_audience=plan.target_audience,
                        is_weekend=is_weekend,
                        is_active=True
                    ).first()

                    # Get current price (try zone pricing first)
                    base_price = 0
                    clip_duration = 30  # Default duration
                    if plan.clips.count() > 0:
                        clip_duration = plan.clips.first().duration

                    # Try zone pricing first
                    zone = get_zone_for_time_slot(time_slot, is_weekend)
                    zone_price = StationZonePrice.query.filter_by(
                        station_id=station.id,
                        zone=zone,
                        is_weekend=is_weekend
                    ).all()

                    # Find best matching duration
                    best_zone_price = None
                    for zp in zone_price:
                        zp_duration = int(zp.duration.replace('s', ''))
                        if zp_duration >= clip_duration:
                            if best_zone_price is None or zp_duration < int(best_zone_price.duration.replace('s', '')):
                                best_zone_price = zp

                    if best_zone_price:
                        base_price = best_zone_price.price

                    # Create captured data record with month-specific seasonal index
                    captured_data = PlanStationData(
                        plan_id=plan.id,
                        station_id=station.id,
                        time_slot=time_slot,
                        is_weekend=is_weekend,
                        month=month,
                        grp=rating.grp if rating else 0,
                        trp=rating.trp if rating else 0,
                        affinity=rating.affinity if rating else 0,
                        base_price=base_price,
                        seasonal_index=seasonal_index
                    )

                    db.session.add(captured_data)

    print(f"Captured data for {len(plan.selected_stations)} stations across {len(time_slots)} time slots (weekday + weekend)")

def get_zone_for_time_slot(time_slot, is_weekend):
    """Map time slot to pricing zone"""
    start_time = time_slot.split('-')[0]
    hour = int(start_time.split(':')[0])

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