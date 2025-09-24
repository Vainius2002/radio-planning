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
    """Export radio plan to Excel file matching radijo-pavyzdys.xlsx format"""
    import xlsxwriter
    from io import BytesIO
    import pandas as pd

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)

    # Clean campaign name for worksheet name (remove newlines, extra spaces, limit length)
    clean_name = plan.campaign_name.replace('\n', '').replace('\r', '').strip() if plan.campaign_name else 'Plan'
    clean_name = ' '.join(clean_name.split())  # Remove extra whitespace
    clean_name = clean_name[:25] if len(clean_name) > 25 else clean_name  # Limit to 25 chars
    worksheet_name = f'{clean_name}_A'

    worksheet = workbook.add_worksheet(worksheet_name)

    # Add formats with enhanced styling
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })

    subheader_format = workbook.add_format({
        'bold': True,
        'bg_color': '#8DB4E2',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })

    info_header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D9E1F2',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })

    info_header_left_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D9E1F2',
        'border': 1,
        'align': 'left',
        'valign': 'vcenter'
    })

    data_format = workbook.add_format({
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })

    data_green_format = workbook.add_format({
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#E2EFDA'
    })

    calendar_header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#FFE699',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter'
    })

    calendar_data_format = workbook.add_format({
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#FFF2CC'
    })

    data_blue_format = workbook.add_format({
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'bg_color': '#DEEBF7'
    })

    info_format = workbook.add_format({
        'bold': True,
        'align': 'left',
        'bg_color': '#D9E1F2',
        'border': 1
    })

    date_format = workbook.add_format({'num_format': 'yyyy.mm.dd', 'border': 1})
    date_left_format = workbook.add_format({'num_format': 'yyyy.mm.dd', 'border': 1, 'bg_color': '#D9E1F2', 'align': 'left'})
    money_format = workbook.add_format({'num_format': '€#,##0.00', 'border': 1, 'align': 'right'})
    money_green_format = workbook.add_format({'num_format': '€#,##0.00', 'border': 1, 'align': 'right', 'bg_color': '#E2EFDA'})
    money_blue_format = workbook.add_format({'num_format': '€#,##0.00', 'border': 1, 'align': 'right', 'bg_color': '#DEEBF7'})
    percent_format = workbook.add_format({'num_format': '0.0%', 'border': 1, 'align': 'center'})
    percent_blue_format = workbook.add_format({'num_format': '0.0%', 'border': 1, 'align': 'center', 'bg_color': '#DEEBF7'})
    number_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right'})
    number_green_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right', 'bg_color': '#E2EFDA'})
    number_blue_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right', 'bg_color': '#DEEBF7'})

    # Helper function to clean text values
    def clean_text(text):
        if not text:
            return ''
        return text.replace('\n', '').replace('\r', '').strip()

    # Write header information with enhanced formatting (rows 0-7)
    # Format A1:C7 range - apply consistent formatting
    for row in range(7):
        for col in range(3):
            worksheet.write(row, col, '', info_header_format)

    # Format H2:I5 range with same color as C3
    for row in range(1, 5):
        for col in range(7, 9):
            worksheet.write(row, col, '', info_header_format)

    # Format P4:P5 range
    for row in range(3, 5):
        worksheet.write(row, 15, '', info_header_format)

    worksheet.write(0, 0, 'Agentūra:', info_format)
    worksheet.merge_range('B1:C1', 'BPN LT', info_header_left_format)

    worksheet.write(1, 0, 'Klientas:', info_format)
    worksheet.merge_range('B2:C2', clean_text(plan.client_brand_name) or 'CLIENT', info_header_left_format)
    worksheet.write(1, 7, 'Tikslinė grupė', info_format)
    worksheet.write(1, 8, clean_text(plan.target_audience), info_header_format)

    worksheet.write(2, 0, 'Produktas:', info_format)
    worksheet.merge_range('B3:C3', clean_text(plan.project_name or plan.campaign_name), info_header_left_format)
    worksheet.write(2, 7, "TG dydis ('000):", info_format)
    worksheet.write(2, 8, '1059.49', info_header_format)  # Placeholder value

    worksheet.write(3, 0, 'Kampanija:', info_format)
    worksheet.merge_range('B4:C4', clean_text(plan.campaign_name) or '', info_header_left_format)
    worksheet.write(3, 7, 'TG dalis (%):', info_format)
    worksheet.write(3, 8, '60.2%', info_header_format)  # TG dalis percentage
    worksheet.write(3, 15, 'Klipo trukmė (-s):', info_header_format)

    worksheet.write(4, 0, 'Laikotarpis:', info_format)
    date_range = f"{plan.start_date.strftime('%Y.%m.%d')}-{plan.end_date.strftime('%m.%d')}"
    worksheet.merge_range('B5:C5', date_range, info_header_left_format)
    worksheet.write(4, 7, 'TG imtis:', info_format)
    worksheet.write(4, 8, '1759.35', info_header_format)  # Placeholder value

    # Get clip duration from the plan
    clip_duration = 30  # Default
    if plan.clips.count() > 0:
        clip_duration = plan.clips.first().duration
    worksheet.write(4, 15, clip_duration, info_header_format)

    worksheet.write(5, 0, 'Šalis:', info_format)
    worksheet.merge_range('B6:C6', 'Lietuva', info_header_left_format)

    worksheet.write(6, 0, 'Savaitės pradžios data', info_format)
    worksheet.merge_range('B7:C7', plan.start_date.strftime('%Y.%m.%d'), info_header_left_format)

    # Write main headers (rows 9-11)
    main_headers_row1 = [
        'Kanalas', 'Laikas', 'Savaitės', 'Klipų', 'Klipo ',
        'GRP', 'TRP', 'Affinity', '1 sec.',
        'Įkainis', 'Sez.', 'Spec.', 'Gross', 'Kaina po',
        'Kaina po', 'Mūsų', 'Kliento'
    ]

    main_headers_row2 = [
        '', '', 'diena', 'skaičius', 'trukmė',
        '', '', '', 'TRP',
        '(EUR)', 'indeksas', 'indeksas', 'kaina', 'mūsų nuolaidos',
        'kliento nuolaidos', 'nuolaida', 'nuolaida'
    ]

    main_headers_row3 = [
        '', '', '', '', '',
        '', '', '', 'kaina',
        '', '', '', '(EUR)', '(EUR)',
        '(EUR)', '(%)', '(%)'
    ]

    # Create format for wrapped text in merged cells
    header_format_wrap = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': True
    })

    # Write main headers with proper styling and merge cells where appropriate
    # First write headers that will be merged (need to write them first before merging)
    worksheet.merge_range('A10:A12', 'Kanalas', header_format)
    worksheet.merge_range('B10:B12', 'Laikas', header_format)
    worksheet.merge_range('C10:C12', 'Savaitės diena', header_format_wrap)  # Use wrap format
    worksheet.merge_range('D10:D12', 'Klipų skaičius', header_format_wrap)
    worksheet.merge_range('E10:E12', 'Klipo trukmė', header_format_wrap)
    worksheet.merge_range('F10:F12', 'GRP', header_format)
    worksheet.merge_range('G10:G12', 'TRP', header_format)
    worksheet.merge_range('H10:H12', 'Affinity', header_format)

    # Merge columns I through Q (8 through 16)
    worksheet.merge_range('I10:I12', '1 sec.\nTRP\nkaina', header_format_wrap)
    worksheet.merge_range('J10:J12', 'Įkainis\n(EUR)', header_format_wrap)
    worksheet.merge_range('K10:K12', 'Sez.\nindeksas', header_format_wrap)
    worksheet.merge_range('L10:L12', 'Spec.\nindeksas', header_format_wrap)
    worksheet.merge_range('M10:M12', 'Gross\nkaina\n(EUR)', header_format_wrap)
    worksheet.merge_range('N10:N12', 'Kaina po\nmūsų nuolaidos\n(EUR)', header_format_wrap)
    worksheet.merge_range('O10:O12', 'Kaina po\nkliento nuolaidos\n(EUR)', header_format_wrap)
    worksheet.merge_range('P10:P12', 'Mūsų\nnuolaida\n(%)', header_format_wrap)
    worksheet.merge_range('Q10:Q12', 'Kliento\nnuolaida\n(%)', header_format_wrap)

    # Add calendar headers starting from column 17
    start_col = 17
    current_date = plan.start_date
    date_cols = {}

    # Track when to write month names
    last_month = None
    month_names = {
        1: 'Sausis', 2: 'Vasaris', 3: 'Kovas', 4: 'Balandis',
        5: 'Gegužė', 6: 'Birželis', 7: 'Liepa', 8: 'Rugpjūtis',
        9: 'Rugsėjis', 10: 'Spalis', 11: 'Lapkritis', 12: 'Gruodis'
    }

    while current_date <= plan.end_date:
        # Write month name when month changes or at the beginning
        if current_date.month != last_month:
            worksheet.write(9, start_col, month_names[current_date.month], calendar_header_format)
            last_month = current_date.month
        else:
            # Empty cell for continuation of same month
            worksheet.write(9, start_col, '', calendar_header_format)

        # Day abbreviations
        day_abbrev = ['Pr', 'An', 'Tr', 'Ke', 'Pe', 'Se', 'Sk'][current_date.weekday()]
        worksheet.write(10, start_col, day_abbrev, calendar_header_format)

        # Write actual date number (day of month)
        worksheet.write(11, start_col, current_date.day, calendar_header_format)

        date_cols[current_date] = start_col
        start_col += 1
        current_date = current_date + pd.Timedelta(days=1)

    # Get all spots with spot_count > 0, grouped by station and time_slot
    from app.models import RadioSpot
    spots_query = RadioSpot.query.filter(
        RadioSpot.plan_id == plan.id,
        RadioSpot.spot_count > 0
    ).order_by('station_id', 'time_slot').all()

    # Group spots by station and time_slot to create summary rows
    spot_groups = {}
    for spot in spots_query:
        key = (spot.station_id, spot.time_slot, spot.is_weekend_row)
        if key not in spot_groups:
            # Calculate special index - use special_position if it contains a numeric value, otherwise default to 1.0
            special_index = 1.0
            if spot.special_position:
                try:
                    special_index = float(spot.special_position)
                except (ValueError, TypeError):
                    special_index = 1.0

            spot_groups[key] = {
                'station_name': clean_text(spot.station.name),
                'time_slot': clean_text(spot.time_slot),
                'weekday': clean_text('VI-VII' if spot.is_weekend_row else 'I-V'),
                'spots_by_date': {},
                'total_spots': 0,
                'grp': spot.grp,
                'trp': spot.trp,
                'affinity': spot.affinity,
                'base_price': spot.base_price,
                'seasonal_index': spot.seasonal_index,
                'special_index': special_index,
                'final_price': spot.final_price,
                'price_per_trp': spot.price_per_trp
            }

        spot_groups[key]['spots_by_date'][spot.date] = spot.spot_count
        spot_groups[key]['total_spots'] += spot.spot_count

    # Write data rows starting from row 12
    row = 12
    for key, group_data in spot_groups.items():
        # Only include rows with total_spots > 0
        if group_data['total_spots'] > 0:
            # Calculate gross price (base_price * seasonal_index * special_index)
            gross_price = group_data['base_price'] * group_data['seasonal_index'] * group_data['special_index']

            # Calculate price after our discount
            price_after_our_discount = gross_price * (1 - plan.our_discount / 100)

            # Calculate price after client discount
            price_after_client_discount = price_after_our_discount * (1 - plan.client_discount / 100)

            # Write main data with color coding
            worksheet.write(row, 0, clean_text(group_data['station_name']), data_format)  # Kanalas
            worksheet.write(row, 1, clean_text(group_data['time_slot']), data_format)  # Laikas
            worksheet.write(row, 2, clean_text(group_data['weekday']), data_format)  # Savaitės diena
            worksheet.write(row, 3, group_data['total_spots'], data_format)  # Klipų skaičius
            worksheet.write(row, 4, clip_duration, data_format)  # Klipo trukmė
            worksheet.write(row, 5, group_data['grp'], number_format)  # GRP
            worksheet.write(row, 6, group_data['trp'], number_format)  # TRP
            worksheet.write(row, 7, group_data['affinity'], number_format)  # Affinity
            worksheet.write(row, 8, group_data['price_per_trp'], number_format)  # 1 sec TRP kaina
            worksheet.write(row, 9, group_data['base_price'], money_format)  # Įkainis
            worksheet.write(row, 10, group_data['seasonal_index'], number_format)  # Sez. indeksas
            worksheet.write(row, 11, group_data['special_index'], number_format)  # Spec. indeksas
            worksheet.write(row, 12, gross_price, money_format)  # Gross kaina

            # Color code columns 13-16 (price and discount columns) with blue background
            worksheet.write(row, 13, price_after_our_discount, money_blue_format)  # Kaina po mūsų nuolaidos
            worksheet.write(row, 14, price_after_client_discount, money_blue_format)  # Kaina po kliento nuolaidos
            worksheet.write(row, 15, plan.our_discount / 100, percent_blue_format)  # Mūsų nuolaida %
            worksheet.write(row, 16, plan.client_discount / 100, percent_blue_format)  # Kliento nuolaida %

            # Write calendar data with distinct calendar background for non-zero spot counts
            for date, spot_count in group_data['spots_by_date'].items():
                if date in date_cols and spot_count > 0:
                    worksheet.write(row, date_cols[date], spot_count, calendar_data_format)

            row += 1

    # Auto-fit columns
    worksheet.set_column(0, 0, 20)  # Station name
    worksheet.set_column(1, 1, 12)  # Time
    worksheet.set_column(2, 2, 8)   # Weekday
    worksheet.set_column(3, 3, 8)   # Spot count
    worksheet.set_column(4, 4, 8)   # Clip duration
    worksheet.set_column(5, 8, 12)  # GRP, TRP, affinity, TRP price
    worksheet.set_column(9, 16, 15) # Price columns and discounts
    worksheet.set_column(17, start_col-1, 12)  # Calendar columns - much wider to prevent ### symbols

    workbook.close()
    output.seek(0)

    return output

def get_live_seasonal_index(station_id, group_id, month):
    """Fetch live seasonal index from external seasonal-adjustments service"""
    import requests
    from bs4 import BeautifulSoup

    try:
        # Fetch seasonal index from external seasonal-adjustments service for this specific group
        seasonal_adjustments_url = f"http://127.0.0.1:5006/groups/{group_id}/seasonal-adjustments"

        response = requests.get(seasonal_adjustments_url, timeout=10)
        if response.status_code == 200:
            # Parse HTML response to extract seasonal index for the specific month
            soup = BeautifulSoup(response.text, 'html.parser')
            print(f"Fetching LIVE seasonal index for station {station_id} (group {group_id}), month {month}")

            # Look for input elements with class "index-value" and find the one for the specific month
            month_inputs = soup.find_all('input', class_='index-value')

            # Find the input for the specific month (month inputs are in order 1-12)
            if month_inputs and 1 <= month <= len(month_inputs):
                month_input = month_inputs[month - 1]  # month-1 because array is 0-indexed
                seasonal_index = float(month_input.get('value', 1.0))
                print(f"Found LIVE seasonal index {seasonal_index} for station {station_id} (group {group_id}), month {month}")
                return seasonal_index

        print(f"Could not fetch LIVE seasonal index for station {station_id} (group {group_id}), month {month}, using default 1.0")
        return 1.0

    except Exception as e:
        print(f"Error fetching LIVE seasonal index for station {station_id} (group {group_id}), month {month}: {str(e)}")
        return 1.0

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
            # Get LIVE seasonal index for this station and month from external seasonal-adjustments service
            seasonal_index = get_live_seasonal_index(station.id, station.group_id, month)
            print(f"Station {station.name} (group {station.group_id}), Month {month}: LIVE seasonal index = {seasonal_index}")

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