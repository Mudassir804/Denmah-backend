# models.py
from sqlalchemy import Text, Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # Import func for timestamps
from database import Base
from datetime import datetime



#Admin 
class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)


# Product models (Existing)
class Product(Base):
    __tablename__ = "products"
    # ... (existing product columns) ...
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    sku = Column(String, unique=True, index=True)
    gender = Column(String)
    category = Column(String)
    color = Column(String)
    description = Column(String)

    # Relationships
    pricing_tiers = relationship("PricingTier", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    email = Column(String)
    rating = Column(Integer)  # 1 to 5
    text = Column(Text)       # The review content
    user_name = Column(String, default="Anonymous") # e.g. "Harry"
    verified = Column(Boolean, default=True) # Mocking verified purchase
    
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="reviews")

class PricingTier(Base):
    __tablename__ = "pricing_tiers"
    # ... (existing pricing tier columns) ...
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    min_quantity = Column(Integer)
    price = Column(Float)

    product = relationship("Product", back_populates="pricing_tiers")

class ProductImage(Base):
    __tablename__ = "product_images"
    # ... (existing image columns) ...
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    image_url = Column(String)
    color = Column(String)
    product = relationship("Product", back_populates="images")


# 🛍️ NEW ORDER MODELS 🛍️

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_sku = Column(String, index=True) # The SKU of the main product
    product_title = Column(String)
    
    # Financial Summary
    total_quantity = Column(Integer, default=0)
    unit_price_tier = Column(Float, default=0.0)
    grand_total = Column(Float)
    
    # Customer/Shipping Information
    email_or_phone = Column(String, index=True)
    country = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    address = Column(String)
    city = Column(String)
    postal_code = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    shipping_method = Column(String)
    
    # Status and Timestamps
    status = Column(String, default="Pending") # e.g., Pending, Confirmed, Shipped, Cancelled
    created_at = Column(DateTime, default=func.now())
    
    # Relationship to individual items
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    
    # Item details
    color_id = Column(String) # The dynamically generated color ID from the frontend
    color_name = Column(String) # The actual color name (e.g., "Red", "Blue")
    size = Column(String)
    quantity = Column(Integer)
    
    # Back relationship
    order = relationship("Order", back_populates="items")


class BlogCategory(Base):
    __tablename__ = "blog_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    posts = relationship("BlogPost", back_populates="category")

class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    excerpt = Column(String)
    author = Column(String, default="Admin")
    content = Column(Text) # For long markdown text
    image_url = Column(String)
    tags = Column(String) # Store as comma-separated string: "Denim,Winter,Style"
    created_at = Column(DateTime, default=datetime.utcnow)
    
    category_id = Column(Integer, ForeignKey("blog_categories.id"))
    category = relationship("BlogCategory", back_populates="posts")