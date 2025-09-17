import pandas as pd
import sys
import os

# Add the app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, RadioGroup, RadioStation, StationPrice, StationRating
from config import Config

def import_ratings_data():
    """Import stations and ratings from reitingu-import.xlsx"""
    app = create_app(Config)

    with app.app_context():
        print("Starting radio stations and ratings import...")

        # Create radio groups based on the pricing file structure
        group_mapping = {
            'M-1': 'Reklamos ekspertai',
            'M-1 Plius': 'Reklamos ekspertai',
            'Lietus': 'Reklamos ekspertai',
            'Gold FM': 'Reklamos ekspertai',
            'Pūkas': 'Reklamos ekspertai',
            'Kelyje': 'Reklamos ekspertai',
            'Laluna': 'Reklamos ekspertai',
            'FM99': 'Reklamos ekspertai',
            'Extra FM': 'Reklamos ekspertai',

            'Power Hit Radio': 'PHR',
            'PHR': 'PHR',

            'Radijo Centras': 'Tango',
            'Radiocentras': 'Tango',
            'Rock FM': 'Tango',
            'Relax FM': 'Tango',
            'Rusradio LT': 'Tango',
            'Easy FM': 'Tango',
            'Zip FM': 'Tango'
        }

        # Create groups
        group_objects = {}
        for group_name in set(group_mapping.values()):
            group = RadioGroup.query.filter_by(name=group_name).first()
            if not group:
                group = RadioGroup(name=group_name)
                db.session.add(group)
                db.session.flush()
                print(f"Created group: {group_name}")
            group_objects[group_name] = group

        # Read ratings data from Excel
        ratings_file = 'reitingu-import.xlsx'
        df = pd.read_excel(ratings_file, sheet_name='Rates')

        print(f"Found {len(df)} records in ratings file")

        # Track stations we've processed
        stations_created = {}
        current_station = None

        # Process each row
        for index, row in df.iterrows():
            station_name = row['RD STOTIS']
            day_type = row['DIENA']  # pr-pn (weekdays) or šš (weekend)
            time_slot = row['LAIKAS']
            grp = row['GRP']
            trp = row['TRP']

            # Check if this row has a station name (some rows continue with NaN for station name)
            if pd.notna(station_name):
                current_station = str(station_name).strip()

                # Create station if it doesn't exist
                if current_station not in stations_created:
                    # Determine group
                    group_name = group_mapping.get(current_station, 'Tango')  # Default to Tango

                    station = RadioStation.query.filter_by(name=current_station).first()
                    if not station:
                        station = RadioStation(
                            name=current_station,
                            group_id=group_objects[group_name].id
                        )
                        db.session.add(station)
                        db.session.flush()
                        print(f"Created station: {current_station} in group {group_name}")

                    stations_created[current_station] = station

            # Skip if no current station or no time slot
            if not current_station or pd.isna(time_slot):
                continue

            # Skip if GRP/TRP values are missing
            if pd.isna(grp) or pd.isna(trp):
                continue

            # Determine if weekend
            is_weekend = str(day_type).strip() == 'šš' if pd.notna(day_type) else False

            # Create rating record
            station = stations_created[current_station]

            # Check if rating already exists
            existing_rating = StationRating.query.filter_by(
                station_id=station.id,
                time_slot=time_slot,
                target_audience='All',
                is_weekend=is_weekend
            ).first()

            if not existing_rating:
                rating = StationRating(
                    station_id=station.id,
                    time_slot=time_slot,
                    target_audience='All',
                    grp=float(grp),
                    trp=float(trp),
                    is_weekend=is_weekend,
                    is_active=True
                )
                db.session.add(rating)

        print("Adding basic price structure...")

        # Add basic price structure for all stations
        time_slots = [
            "07:00-07:30", "07:30-08:00", "08:00-08:30", "08:30-09:00",
            "09:00-09:30", "09:30-10:00", "10:00-10:30", "10:30-11:00",
            "11:00-11:30", "11:30-12:00", "12:00-12:30", "12:30-13:00",
            "13:00-13:30", "13:30-14:00", "14:00-14:30", "14:30-15:00",
            "15:00-15:30", "15:30-16:00", "16:00-16:30", "16:30-17:00",
            "17:00-17:30", "17:30-18:00", "18:00-18:30", "18:30-19:00"
        ]

        for station in stations_created.values():
            for time_slot in time_slots:
                # Base price depending on time
                hour = int(time_slot.split(':')[0])

                if 7 <= hour < 9:
                    base_price = 150  # Morning prime
                elif 9 <= hour < 12:
                    base_price = 100  # Morning
                elif 12 <= hour < 14:
                    base_price = 120  # Lunch
                elif 14 <= hour < 17:
                    base_price = 90   # Afternoon
                else:
                    base_price = 140  # Evening prime

                # Adjust by station popularity
                if station.name in ['M-1', 'Power Hit Radio', 'Radijo Centras']:
                    base_price *= 1.5  # Premium stations
                elif station.name in ['Rock FM', 'Relax FM', 'Gold FM']:
                    base_price *= 1.2  # Popular stations

                # Check if price already exists
                existing_weekday = StationPrice.query.filter_by(
                    station_id=station.id,
                    time_slot=time_slot,
                    is_weekend=False
                ).first()

                if not existing_weekday:
                    # Weekday price
                    price = StationPrice(
                        station_id=station.id,
                        time_slot=time_slot,
                        price=base_price,
                        is_weekend=False,
                        is_active=True
                    )
                    db.session.add(price)

                existing_weekend = StationPrice.query.filter_by(
                    station_id=station.id,
                    time_slot=time_slot,
                    is_weekend=True
                ).first()

                if not existing_weekend:
                    # Weekend price (typically 20% lower)
                    weekend_price = StationPrice(
                        station_id=station.id,
                        time_slot=time_slot,
                        price=base_price * 0.8,
                        is_weekend=True,
                        is_active=True
                    )
                    db.session.add(weekend_price)

        # Commit all changes
        db.session.commit()

        print("\n=== Import Summary ===")
        print(f"Groups created: {RadioGroup.query.count()}")
        print(f"Stations created: {RadioStation.query.count()}")
        print(f"Ratings imported: {StationRating.query.count()}")
        print(f"Prices imported: {StationPrice.query.count()}")

        print("\n=== Stations by Group ===")
        for group in RadioGroup.query.all():
            stations = RadioStation.query.filter_by(group_id=group.id).all()
            print(f"{group.name}: {[s.name for s in stations]}")

        print("\nImport completed successfully!")

if __name__ == '__main__':
    import_ratings_data()