from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class RadioGroup(db.Model):
    __tablename__ = 'radio_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    stations = db.relationship('RadioStation', backref='group', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RadioGroup {self.name}>'

class RadioStation(db.Model):
    __tablename__ = 'radio_stations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('radio_groups.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    prices = db.relationship('StationPrice', backref='station', lazy='dynamic', cascade='all, delete-orphan')
    ratings = db.relationship('StationRating', backref='station', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RadioStation {self.name}>'

    def get_current_price(self, time_slot, is_weekend=False):
        """Get current price for specific time slot"""
        price = self.prices.filter_by(
            time_slot=time_slot,
            is_weekend=is_weekend,
            is_active=True
        ).first()
        return price.price if price else 0

class StationPrice(db.Model):
    __tablename__ = 'station_prices'

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_stations.id'), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)  # e.g., '07:00-08:00'
    price = db.Column(db.Float, nullable=False)
    is_weekend = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<StationPrice {self.station.name} {self.time_slot}: {self.price}>'

class StationRating(db.Model):
    __tablename__ = 'station_ratings'

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_stations.id'), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    target_audience = db.Column(db.String(50), nullable=False)  # e.g., '18-49', '25-54', 'All'
    grp = db.Column(db.Float, nullable=False)
    trp = db.Column(db.Float, nullable=False)
    is_weekend = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def affinity(self):
        """Calculate affinity (TRP / GRP)"""
        if self.grp > 0:
            return self.trp / self.grp
        return 0

    def __repr__(self):
        return f'<StationRating {self.station.name} {self.time_slot}: GRP={self.grp}, TRP={self.trp}>'

class SeasonalIndex(db.Model):
    __tablename__ = 'seasonal_indices'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    index_value = db.Column(db.Float, nullable=False, default=1.0)
    group_id = db.Column(db.Integer, db.ForeignKey('radio_groups.id'), nullable=True)  # None for global indices
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    group = db.relationship('RadioGroup', backref='seasonal_indices')

    def __repr__(self):
        return f'<SeasonalIndex Month {self.month}: {self.index_value}>'

# Association table for many-to-many relationship between plans and stations
plan_stations = db.Table('plan_stations',
    db.Column('plan_id', db.Integer, db.ForeignKey('radio_plans.id'), primary_key=True),
    db.Column('station_id', db.Integer, db.ForeignKey('radio_stations.id'), primary_key=True)
)

class RadioPlan(db.Model):
    __tablename__ = 'radio_plans'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, nullable=False)  # From projects-crm
    campaign_name = db.Column(db.String(200))
    project_id = db.Column(db.Integer)
    project_name = db.Column(db.String(200))
    client_brand_id = db.Column(db.Integer)
    client_brand_name = db.Column(db.String(200))

    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    target_audience = db.Column(db.String(50), nullable=False)
    our_discount = db.Column(db.Float, default=0)  # Percentage
    client_discount = db.Column(db.Float, default=0)  # Percentage

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    spots = db.relationship('RadioSpot', backref='plan', lazy='dynamic', cascade='all, delete-orphan')
    clips = db.relationship('RadioClip', backref='plan', lazy='dynamic', cascade='all, delete-orphan')
    selected_stations = db.relationship('RadioStation', secondary=plan_stations, lazy='subquery',
                                      backref=db.backref('plans', lazy=True))

    def __repr__(self):
        return f'<RadioPlan {self.campaign_name}>'

class RadioClip(db.Model):
    __tablename__ = 'radio_clips'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('radio_plans.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # In seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<RadioClip {self.name} ({self.duration}s)>'

class RadioSpot(db.Model):
    __tablename__ = 'radio_spots'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('radio_plans.id'), nullable=False)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_stations.id'), nullable=False)
    clip_id = db.Column(db.Integer, db.ForeignKey('radio_clips.id'))

    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    weekday = db.Column(db.String(20))
    special_position = db.Column(db.String(100))

    # Counts and durations
    spot_count = db.Column(db.Integer, default=1)
    clip_duration = db.Column(db.Integer)  # seconds

    # Ratings
    grp = db.Column(db.Float, default=0)
    trp = db.Column(db.Float, default=0)
    affinity = db.Column(db.Float, default=0)

    # Pricing
    base_price = db.Column(db.Float, default=0)
    seasonal_index = db.Column(db.Float, default=1.0)
    price_with_index = db.Column(db.Float, default=0)
    our_discount_amount = db.Column(db.Float, default=0)
    client_discount_amount = db.Column(db.Float, default=0)
    final_price = db.Column(db.Float, default=0)
    price_per_trp = db.Column(db.Float, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    station = db.relationship('RadioStation', backref='spots')
    clip = db.relationship('RadioClip', backref='spots')

    def calculate_price(self, our_discount=0, client_discount=0):
        """Calculate all price components"""
        # Get base price from station
        is_weekend = self.date.weekday() >= 5  # Saturday = 5, Sunday = 6
        self.base_price = self.station.get_current_price(self.time_slot, is_weekend)

        # Apply seasonal index
        month = self.date.month
        # First try to get group-specific seasonal index
        group_id = self.station.group_id if self.station else None
        if group_id:
            seasonal = SeasonalIndex.query.filter_by(month=month, group_id=group_id, is_active=True).first()
        else:
            seasonal = None

        # Fall back to global seasonal index if no group-specific one exists
        if not seasonal:
            seasonal = SeasonalIndex.query.filter_by(month=month, group_id=None, is_active=True).first()

        if seasonal:
            self.seasonal_index = seasonal.index_value

        self.price_with_index = self.base_price * self.seasonal_index

        # Apply discounts
        price_after_our = self.price_with_index * (1 - our_discount / 100)
        self.final_price = price_after_our * (1 - client_discount / 100)

        # Calculate price per TRP using formula: basePrice / TRP / 100
        if self.trp > 0:
            self.price_per_trp = self.base_price / self.trp / 100

        return self.final_price

    def __repr__(self):
        station_name = self.station.name if self.station else f'Station#{self.station_id}'
        return f'<RadioSpot {station_name} {self.date} {self.time_slot}>'

class StationZonePrice(db.Model):
    """Zone-based pricing for radio stations"""
    __tablename__ = 'station_zone_prices'

    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_stations.id'), nullable=False)
    zone = db.Column(db.String(10), nullable=False)  # A, B, C, D
    duration = db.Column(db.String(10), nullable=False)  # 15s, 20s, 30s, 40s, 60s
    price = db.Column(db.Float, default=0.0)
    is_weekend = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    station = db.relationship('RadioStation', backref='zone_prices')

    def __repr__(self):
        return f'<StationZonePrice {self.station.name} Zone:{self.zone} Duration:{self.duration}>'

class PlanStationData(db.Model):
    """Captured station data for a specific plan - ratings, prices, seasonal indices"""
    __tablename__ = 'plan_station_data'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('radio_plans.id'), nullable=False)
    station_id = db.Column(db.Integer, db.ForeignKey('radio_stations.id'), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    is_weekend = db.Column(db.Boolean, default=False)

    # Captured ratings (from StationRating at plan creation time)
    grp = db.Column(db.Float, default=0)
    trp = db.Column(db.Float, default=0)
    affinity = db.Column(db.Float, default=0)

    # Captured pricing (from StationPrice/StationZonePrice at plan creation time)
    base_price = db.Column(db.Float, default=0)
    seasonal_index = db.Column(db.Float, default=1.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    plan = db.relationship('RadioPlan', backref='captured_station_data')
    station = db.relationship('RadioStation', backref='plan_data')

    def __repr__(self):
        return f'<PlanStationData Plan:{self.plan_id} Station:{self.station_id} Slot:{self.time_slot}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<User {self.username}>'