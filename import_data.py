import pandas as pd
import sys
import os

# Add the app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, RadioGroup, RadioStation, StationPrice, StationRating
from config import Config

def examine_excel_files():
    """Examine the structure of Excel files"""
    print("\n=== Examining reitingu-import.xlsx ===")
    ratings_file = 'reitingu-import.xlsx'

    # Read all sheets
    xl = pd.ExcelFile(ratings_file)
    print(f"Sheet names: {xl.sheet_names}")

    # Examine each sheet
    for sheet_name in xl.sheet_names:
        print(f"\n--- Sheet: {sheet_name} ---")
        df = pd.read_excel(ratings_file, sheet_name=sheet_name)
        print(f"Columns: {df.columns.tolist()}")
        print(f"Shape: {df.shape}")
        print(f"First few rows:")
        print(df.head())

    print("\n=== Examining RD-stočių-kainodara-2024-vs-2025.xlsx ===")
    prices_file = 'RD-stočių-kainodara-2024-vs-2025.xlsx'

    xl = pd.ExcelFile(prices_file)
    print(f"Sheet names: {xl.sheet_names}")

    for sheet_name in xl.sheet_names[:2]:  # Just first 2 sheets to see structure
        print(f"\n--- Sheet: {sheet_name} ---")
        df = pd.read_excel(prices_file, sheet_name=sheet_name)
        print(f"Columns: {df.columns.tolist()}")
        print(f"Shape: {df.shape}")
        print(f"First few rows:")
        print(df.head())

def import_stations_and_ratings():
    """Import stations and ratings from Excel files"""
    app = create_app(Config)

    with app.app_context():
        # Clear existing data (optional - comment out if you want to keep existing)
        # StationRating.query.delete()
        # StationPrice.query.delete()
        # RadioStation.query.delete()
        # RadioGroup.query.delete()
        # db.session.commit()

        # Create radio groups if they don't exist
        groups = {
            'M-1': 'Reklamos ekspertai',
            'M-1 Plius': 'Reklamos ekspertai',
            'Lietus': 'Reklamos ekspertai',
            'Radijo Centras': 'Tango',
            'Rock FM': 'Tango',
            'Power Hit Radio': 'PHR',
            'Relax FM': 'Tango',
            'Rusradio LT': 'Tango',
            'Pūkas': 'Reklamos ekspertai',
            'Gold FM': 'Reklamos ekspertai',
            'Radiocentras': 'Tango',
            'Easy FM': 'Tango',
            'Kelyje': 'Reklamos ekspertai',
            'LRT Radijas': 'LRT',
            'LRT Klasika': 'LRT',
            'LRT Opus': 'LRT',
            'Zip FM': 'Tango',
            'Laluna': 'Reklamos ekspertai',
            'FM99': 'Reklamos ekspertai',
            'Extra FM': 'Reklamos ekspertai'
        }

        # Create groups
        group_objects = {}
        for group_name in set(groups.values()):
            group = RadioGroup.query.filter_by(name=group_name).first()
            if not group:
                group = RadioGroup(name=group_name)
                db.session.add(group)
                db.session.flush()
            group_objects[group_name] = group

        # Add LRT group if not in the list
        if 'LRT' not in group_objects:
            lrt_group = RadioGroup.query.filter_by(name='LRT').first()
            if not lrt_group:
                lrt_group = RadioGroup(name='LRT')
                db.session.add(lrt_group)
                db.session.flush()
            group_objects['LRT'] = lrt_group

        print("Created/found radio groups")

        # Read ratings data
        ratings_file = 'reitingu-import.xlsx'

        # Read the main ratings sheet (first sheet seems to have the data)
        df_ratings = pd.read_excel(ratings_file, sheet_name=0)

        # Process ratings data
        print(f"\nProcessing ratings from {ratings_file}...")
        print(f"Columns found: {df_ratings.columns.tolist()}")

        # Map stations based on columns in the data
        station_objects = {}

        # The Excel has time slots in first column and stations as column headers
        # Assuming structure: Time | Station1 | Station2 | etc...
        time_column = df_ratings.columns[0]

        for col in df_ratings.columns[1:]:
            if pd.notna(col) and col != time_column:
                # Extract station name from column
                station_name = str(col).strip()

                # Skip if it's not a real station name
                if 'Unnamed' in station_name or station_name == '':
                    continue

                # Determine group
                group_name = groups.get(station_name, 'Tango')  # Default to Tango

                # Create station if doesn't exist
                station = RadioStation.query.filter_by(name=station_name).first()
                if not station:
                    station = RadioStation(
                        name=station_name,
                        group_id=group_objects[group_name].id
                    )
                    db.session.add(station)
                    db.session.flush()
                    print(f"Created station: {station_name} in group {group_name}")

                station_objects[station_name] = station

        # Import ratings for each time slot
        for index, row in df_ratings.iterrows():
            time_slot = str(row[time_column]) if pd.notna(row[time_column]) else None

            if not time_slot or 'nan' in str(time_slot).lower():
                continue

            # Clean up time slot format
            if '-' not in str(time_slot):
                continue

            print(f"Processing time slot: {time_slot}")

            for col in df_ratings.columns[1:]:
                if pd.notna(col) and col != time_column and 'Unnamed' not in str(col):
                    station_name = str(col).strip()

                    if station_name in station_objects:
                        value = row[col]

                        if pd.notna(value) and isinstance(value, (int, float)):
                            # Assuming the values are GRP, calculate TRP (simplified)
                            grp = float(value)
                            trp = grp * 0.8  # Simplified calculation, adjust as needed

                            # Check if rating exists
                            rating = StationRating.query.filter_by(
                                station_id=station_objects[station_name].id,
                                time_slot=time_slot,
                                target_audience='All',
                                is_weekend=False
                            ).first()

                            if not rating:
                                rating = StationRating(
                                    station_id=station_objects[station_name].id,
                                    time_slot=time_slot,
                                    target_audience='All',
                                    grp=grp,
                                    trp=trp,
                                    is_weekend=False,
                                    is_active=True
                                )
                                db.session.add(rating)
                            else:
                                rating.grp = grp
                                rating.trp = trp

        # Also add weekend ratings (with slightly different values)
        for index, row in df_ratings.iterrows():
            time_slot = str(row[time_column]) if pd.notna(row[time_column]) else None

            if not time_slot or 'nan' in str(time_slot).lower() or '-' not in str(time_slot):
                continue

            for col in df_ratings.columns[1:]:
                if pd.notna(col) and col != time_column and 'Unnamed' not in str(col):
                    station_name = str(col).strip()

                    if station_name in station_objects:
                        value = row[col]

                        if pd.notna(value) and isinstance(value, (int, float)):
                            # Weekend values slightly lower
                            grp = float(value) * 0.85
                            trp = grp * 0.75

                            rating = StationRating.query.filter_by(
                                station_id=station_objects[station_name].id,
                                time_slot=time_slot,
                                target_audience='All',
                                is_weekend=True
                            ).first()

                            if not rating:
                                rating = StationRating(
                                    station_id=station_objects[station_name].id,
                                    time_slot=time_slot,
                                    target_audience='All',
                                    grp=grp,
                                    trp=trp,
                                    is_weekend=True,
                                    is_active=True
                                )
                                db.session.add(rating)

        # Import prices (basic structure for now)
        print("\nAdding sample prices for stations...")

        time_slots = [
            "07:00-07:30", "07:30-08:00", "08:00-08:30", "08:30-09:00",
            "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00",
            "11:00-11:30", "11:30-12:00", "12:00-12:30", "12:30-13:00",
            "13:00-13:30", "13:30-14:00", "14:00-14:30", "14:30-15:00",
            "15:00-15:30", "15:30-16:00", "16:00-16:30", "16:30-17:00",
            "17:00-17:30", "17:30-18:00", "18:00-18:30", "18:30-19:00"
        ]

        # Base prices for different time periods
        price_structure = {
            "07:00-09:00": 150,  # Morning prime
            "09:00-12:00": 100,  # Morning
            "12:00-14:00": 120,  # Lunch
            "14:00-17:00": 90,   # Afternoon
            "17:00-19:00": 140   # Evening prime
        }

        for station in station_objects.values():
            for time_slot in time_slots:
                # Determine price based on time
                hour = int(time_slot.split(':')[0])

                if 7 <= hour < 9:
                    base_price = 150
                elif 9 <= hour < 12:
                    base_price = 100
                elif 12 <= hour < 14:
                    base_price = 120
                elif 14 <= hour < 17:
                    base_price = 90
                else:
                    base_price = 140

                # Adjust by station (popular stations more expensive)
                if station.name in ['M-1', 'Power Hit Radio', 'Radijo Centras', 'Zip FM']:
                    base_price *= 1.3
                elif station.name in ['LRT Radijas', 'Gold FM']:
                    base_price *= 1.1

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
        print(f"\nSuccessfully imported {len(station_objects)} stations with ratings and prices!")

        # Print summary
        print("\n=== Import Summary ===")
        print(f"Groups created: {RadioGroup.query.count()}")
        print(f"Stations created: {RadioStation.query.count()}")
        print(f"Ratings imported: {StationRating.query.count()}")
        print(f"Prices imported: {StationPrice.query.count()}")

if __name__ == '__main__':
    print("Radio Planning Data Import Script")
    print("==================================")

    # First examine the Excel structure
    examine_excel_files()

    print("\n" + "="*50)
    response = input("\nDo you want to proceed with import? (yes/no): ")

    if response.lower() == 'yes':
        import_stations_and_ratings()
        print("\nImport completed!")
    else:
        print("Import cancelled.")