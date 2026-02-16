from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload, aliased # 🎯 FIX: Explicitly importing aliased here
from sqlalchemy import func, cast, String, select
from typing import List, Optional, Dict, Any
from email_utils import send_contact_form_email
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
from datetime import datetime

# Assuming you have database, models, schemas, and email_utils defined
import models, schemas
from database import SessionLocal, engine, get_db
from email_utils import send_email # Assuming this utility exists
from schemas import OrderOut, OrderItemOut, OrderSubmissionRequest

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

origins = [
    "http://localhost:5173", # Add your React app's URL here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
UPLOAD_DIRECTORY = "static/images"


# --- EXISTING ENDPOINTS ---

@app.post("/contact-us/")
async def contact_us_endpoint(contact_data: schemas.ContactRequest):
    """
    Endpoint for customers to send messages via the footer form.
    """
    # Construct a subject line that includes the customer's name
    full_subject = f"Footer Contact: {contact_data.subject} from {contact_data.customer_name}"
    
    result = send_contact_form_email(
        customer_email=contact_data.customer_email,
        subject=full_subject,
        message_body=contact_data.message
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    return {"message": "Message received. We will contact you shortly."}

@app.post("/products/", response_model=schemas.ProductOut)
async def create_product(
    title: str = Form(...),
    sku: str = Form(...),
    gender: str = Form(...),
    category: str = Form(...),
    color: str = Form(...),
    description: Optional[str] = Form(None),
    min_quantities_str: str = Form(..., alias="min_quantities"),
    prices_str: str = Form(..., alias="prices"),
    image_colors_str: str = Form(..., alias="image_colors"), 
    images: List[UploadFile] = File([]),
    db: Session = Depends(get_db)
):
    try:
        min_quantities = [int(q.strip()) for q in min_quantities_str.split(',') if q.strip()]
        prices = [float(p.strip()) for p in prices_str.split(',') if p.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid pricing format")

    image_colors = [c.strip() for c in image_colors_str.split(',') if c.strip()]

    if len(images) != len(image_colors):
        raise HTTPException(status_code=400, detail=f"You uploaded {len(images)} images but provided {len(image_colors)} color names. They must match.")

    db_product = db.query(models.Product).filter(models.Product.sku == sku).first()
    if db_product:
        raise HTTPException(status_code=400, detail="SKU already registered")

    db_product = models.Product(
        title=title, sku=sku, gender=gender, category=category, color=color, description=description
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    for i in range(len(min_quantities)):
        db_pricing_tier = models.PricingTier(product_id=db_product.id, min_quantity=min_quantities[i], price=prices[i])
        db.add(db_pricing_tier)

    os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
    for image_file, color_name in zip(images, image_colors):
        file_extension = os.path.splitext(image_file.filename)[1]
        unique_filename = f"{sku}_{color_name}_{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIRECTORY, unique_filename)
        
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(image_file.file, buffer)
        finally:
            image_file.file.close()

        image_url = f"/static/images/{unique_filename}" 

        db_product_image = models.ProductImage(
            product_id=db_product.id,
            image_url=image_url,
            color=color_name
        )
        db.add(db_product_image)
        
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products/", response_model=List[schemas.ProductOut])
async def read_products(db: Session = Depends(get_db)):
    products = db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).all()
    return products

@app.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return

@app.get("/specific/products/", response_model=List[schemas.ProductOut])
async def read_specific_products(
    gender: Optional[str] = None, 
    category: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    query = db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    )
    if gender:
        query = query.filter(models.Product.gender == gender)
    if category:
        query = query.filter(models.Product.category == category)
    products = query.all()
    return products

@app.get("/products/{product_id}", response_model=schemas.ProductOut)
async def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).filter(models.Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ----------------------------------------------------------------------
# 🛍️ NEW: ORDER SUBMISSION ENDPOINT 🛍️
# ----------------------------------------------------------------------

@app.post("/orders/submit/", response_model=schemas.OrderOut, status_code=201)
async def submit_order(
    request: schemas.OrderSubmissionRequest, 
    db: Session = Depends(get_db)
):
    # Extract data
    customer_info = request.customerInfo
    order_details = request.orderDetails
    
    # Map front-end color ID to real color name
    color_map = {c['id']: c['name'] for c in order_details.productDetails['colors']}
    
    # 1. Create the main Order entry
    db_order = models.Order(
        # General/Financial details
        product_sku=order_details.productDetails['sku'],
        product_title=order_details.productDetails['title'],
        total_quantity=order_details.totalQuantity,
        unit_price_tier=order_details.unitPrice,
        grand_total=order_details.subtotal,
        
        # Customer details
        email_or_phone=customer_info.emailOrPhone,
        first_name=customer_info.firstName,
        last_name=customer_info.lastName,
        address=customer_info.address,
        city=customer_info.city,
        country=customer_info.country,
        postal_code=customer_info.postalCode,
        phone=customer_info.phone,
        shipping_method=customer_info.shippingMethod,
        
        status="Confirmed"
    )
    
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    # 2. Create the OrderItem entries
    for item in order_details.cartItems:
        color_name = color_map.get(item.colorId, item.colorId) 
        
        db_item = models.OrderItem(
            order_id=db_order.id,
            color_id=item.colorId,
            color_name=color_name,
            size=item.size,
            quantity=item.qty
        )
        db.add(db_item)
        
    db.commit()
    db.refresh(db_order)

    return db_order


@app.get("/orders/", response_model=List[OrderOut])
async def read_orders(db: Session = Depends(get_db)):
    """
    Retrieve all orders with their associated line items (order_items)
    """
    orders = db.query(models.Order).options(
        joinedload(models.Order.items)
    ).order_by(models.Order.created_at.desc()).all()

    for order in orders:
        # We attach an invoice number for the frontend UI.
        order.invoice = f"INV-{order.id:06}"
    return orders


# ----------------------------------------------------------------------
# 📈 NEW: CUSTOMER AGGREGATION ENDPOINT 📈
# ----------------------------------------------------------------------

@app.get("/customers/", response_model=List[schemas.CustomerOut])
async def read_customers(db: Session = Depends(get_db)):
    """
    Retrieves and aggregates customer data from the Orders table.
    Groups orders by the unique customer ID (email_or_phone) 
    to calculate total spent and last order date.
    """
    
    # --- 1. Subquery: Aggregate metrics (Total Spent, Last Order Date, Latest Order ID) ---
    subquery = db.query(
        models.Order.email_or_phone.label('customer_id'),
        func.max(models.Order.id).label('latest_order_id'), 
        func.sum(models.Order.grand_total).label('totalSpent'),
        func.max(models.Order.created_at).label('lastOrder')
    ).group_by(models.Order.email_or_phone).subquery()
    
    # 🎯 FIX APPLIED: Use aliased() is correctly defined in the imports.
    orders_alias = aliased(models.Order)
    
    query = db.query(
        subquery.c.customer_id.label('id'),
        
        # Fetch the customer details associated with the latest order ID
        orders_alias.first_name,
        orders_alias.last_name,
        orders_alias.country,
        orders_alias.city,
        orders_alias.phone,
        
        # Aggregated fields
        subquery.c.totalSpent,
        subquery.c.lastOrder
        
    ).join(
        orders_alias, 
        orders_alias.id == subquery.c.latest_order_id
    ).order_by(subquery.c.lastOrder.desc())
    
    results = query.all()
    
    customers_data = []
    for row in results:
        is_email = "@" in row.id
        email = row.id if is_email else None
        phone = row.phone if row.phone else (row.id if not is_email else None)

        full_name = f"{row.first_name or ''} {row.last_name or ''}".strip()
        
        customers_data.append(schemas.CustomerOut(
            id=row.id,
            name=full_name or row.id,
            email=email,
            phone=phone,
            country=row.country,
            city=row.city,
            totalSpent=row.totalSpent,
            lastOrder=row.lastOrder
        ))
        
    return customers_data


@app.put("/orders/{order_id}/status")
async def update_order_status(order_id: int, status_update: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    """
    Update the status of a specific order.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.status = status_update.status
    db.commit()
    db.refresh(order)
    
    return {"message": "Status updated successfully", "id": order.id, "status": order.status}


# ...existing code...
@app.get("/search/product/{product_name}", response_model=List[schemas.ProductOut])
def search_product_by_name(product_name: str, db: Session = Depends(get_db), limit: int = 50):
    """
    Search for products by name (case-insensitive, partial match).
    """
    search_raw = product_name or ""
    # escape SQL wildcard characters
    escaped = search_raw.replace("%", "\\%").replace("_", "\\_")
    search_pattern = f"%{escaped}%"

    products = db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).filter(
        cast(models.Product.title, String).ilike(search_pattern, escape='\\')
    ).limit(limit).all()

    return products


# Blog Category Endpoints

@app.post("/blog/categories/", response_model=schemas.BlogCategoryOut)
def create_blog_category(category: schemas.BlogCategoryCreate, db: Session = Depends(get_db)):
    # Check if category exists
    existing = db.query(models.BlogCategory).filter(models.BlogCategory.name == category.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    
    db_category = models.BlogCategory(name=category.name)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

@app.get("/blog/categories/", response_model=List[schemas.BlogCategoryOut])
def read_blog_categories(db: Session = Depends(get_db)):
    return db.query(models.BlogCategory).all()

# ==========================================
# 📰 BLOG POST ENDPOINTS
# ==========================================

@app.post("/blog/posts/", response_model=schemas.BlogPostOut)
def create_blog_post(
    title: str = Form(...),
    description: str = Form(...), # Maps to 'excerpt' in model if needed, or description
    content: str = Form(...),
    category: str = Form(...),    # Receiving category Name from frontend
    author: str = Form(...),
    tags: str = Form(...),
    is_published: bool = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. Handle Category (Find ID by name)
    # Note: Frontend sends category Name. We find the ID.
    db_category = db.query(models.BlogCategory).filter(models.BlogCategory.name == category).first()
    if not db_category:
        # Auto-create category if it doesn't exist (optional feature)
        db_category = models.BlogCategory(name=category)
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
    
    # 2. Save Image
    os.makedirs("static/images", exist_ok=True)
    file_extension = os.path.splitext(image.filename)[1]
    unique_filename = f"blog_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join("static/images", unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    
    image_url = f"/static/images/{unique_filename}"

    # 3. Create Post
    new_post = models.BlogPost(
        title=title,
        excerpt=description, # Mapping frontend 'description' to model 'excerpt'
        author=author,
        content=content,
        tags=tags,
        category_id=db_category.id,
        image_url=image_url
        # is_published is not in our previous model, assume all posted are published or add column
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post

@app.get("/blog/posts/", response_model=List[schemas.BlogPostOut])
def read_blog_posts(db: Session = Depends(get_db)):
    return db.query(models.BlogPost).options(joinedload(models.BlogPost.category)).all()

@app.delete("/blog/posts/{post_id}", status_code=204)
def delete_blog_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db.delete(post)
    db.commit()
    return



@app.post("/products/{product_id}/reviews/", response_model=schemas.ReviewOut)
def create_review(product_id: int, review: schemas.ReviewCreate, db: Session = Depends(get_db)):
    """
    Create a new review for a specific product.
    """
    # Verify product exists
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db_review = models.Review(
        product_id=product_id,
        rating=review.rating,
        text=review.text,
        user_name=review.user_name,
        email = review.email,
        verified=True 
    )
    
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


@app.get("/products/{product_id}/reviews/", response_model=List[schemas.ReviewOut])
def read_reviews(product_id: int, db: Session = Depends(get_db)):
    """
    Get all reviews for a specific product, sorted by newest first.
    """
    reviews = db.query(models.Review)\
        .filter(models.Review.product_id == product_id)\
        .order_by(models.Review.created_at.desc())\
        .all()
    return reviews