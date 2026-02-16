import os
import shutil
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, cast, String, select
from sqlalchemy.orm import Session, joinedload, aliased

# Local imports
import models
import schemas
from database import SessionLocal, engine, get_db
from email_utils import send_contact_form_email, send_email

# --- DATABASE INITIALIZATION ---
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Denmah Backend API")

# --- CONFIGURATION & MIDDLEWARE ---
origins = [
    "http://localhost:5173",  # React Vite default port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files Setup
UPLOAD_DIRECTORY = "static/images"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ==========================================
# 📧 CONTACT & UTILITIES
# ==========================================

@app.post("/contact-us/")
async def contact_us_endpoint(contact_data: schemas.ContactRequest):
    """Endpoint for customers to send messages via the footer form."""
    full_subject = f"Footer Contact: {contact_data.subject} from {contact_data.customer_name}"
    
    result = send_contact_form_email(
        customer_email=contact_data.customer_email,
        subject=full_subject,
        message_body=contact_data.message
    )
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    
    return {"message": "Message received. We will contact you shortly."}


# ==========================================
# 👕 PRODUCT MANAGEMENT
# ==========================================

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
        raise HTTPException(status_code=400, detail=f"Mismatch: {len(images)} images vs {len(image_colors)} colors.")

    db_product = db.query(models.Product).filter(models.Product.sku == sku).first()
    if db_product:
        raise HTTPException(status_code=400, detail="SKU already registered")

    db_product = models.Product(
        title=title, sku=sku, gender=gender, category=category, color=color, description=description
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    # Add Pricing Tiers
    for i in range(len(min_quantities)):
        db_pricing_tier = models.PricingTier(product_id=db_product.id, min_quantity=min_quantities[i], price=prices[i])
        db.add(db_pricing_tier)

    # Handle Images
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
        db_product_image = models.ProductImage(product_id=db_product.id, image_url=image_url, color=color_name)
        db.add(db_product_image)
        
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products/", response_model=List[schemas.ProductOut])
async def read_products(db: Session = Depends(get_db)):
    return db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).all()

@app.get("/products/{product_id}", response_model=schemas.ProductOut)
async def read_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).filter(models.Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

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
    return query.all()

@app.get("/search/product/{product_name}", response_model=List[schemas.ProductOut])
def search_product_by_name(product_name: str, db: Session = Depends(get_db), limit: int = 50):
    search_raw = product_name or ""
    escaped = search_raw.replace("%", "\\%").replace("_", "\\_")
    search_pattern = f"%{escaped}%"

    return db.query(models.Product).options(
        joinedload(models.Product.images),
        joinedload(models.Product.pricing_tiers)
    ).filter(
        cast(models.Product.title, String).ilike(search_pattern, escape='\\')
    ).limit(limit).all()

@app.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    db_product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return


# ==========================================
# 🛍️ ORDER MANAGEMENT
# ==========================================

@app.post("/orders/submit/", response_model=schemas.OrderOut, status_code=201)
async def submit_order(request: schemas.OrderSubmissionRequest, db: Session = Depends(get_db)):
    customer_info = request.customerInfo
    order_details = request.orderDetails
    color_map = {c['id']: c['name'] for c in order_details.productDetails['colors']}
    
    db_order = models.Order(
        product_sku=order_details.productDetails['sku'],
        product_title=order_details.productDetails['title'],
        total_quantity=order_details.totalQuantity,
        unit_price_tier=order_details.unitPrice,
        grand_total=order_details.subtotal,
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

@app.get("/orders/", response_model=List[schemas.OrderOut])
async def read_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).options(
        joinedload(models.Order.items)
    ).order_by(models.Order.created_at.desc()).all()

    for order in orders:
        order.invoice = f"INV-{order.id:06}"
    return orders

@app.put("/orders/{order_id}/status")
async def update_order_status(order_id: int, status_update: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.status = status_update.status
    db.commit()
    db.refresh(order)
    return {"message": "Status updated", "id": order.id, "status": order.status}


# ==========================================
# 📈 CUSTOMER ANALYTICS
# ==========================================

@app.get("/customers/", response_model=List[schemas.CustomerOut])
async def read_customers(db: Session = Depends(get_db)):
    """Groups orders by customer ID to calculate spending metrics."""
    subquery = db.query(
        models.Order.email_or_phone.label('customer_id'),
        func.max(models.Order.id).label('latest_order_id'), 
        func.sum(models.Order.grand_total).label('totalSpent'),
        func.max(models.Order.created_at).label('lastOrder')
    ).group_by(models.Order.email_or_phone).subquery()
    
    orders_alias = aliased(models.Order)
    
    results = db.query(
        subquery.c.customer_id.label('id'),
        orders_alias.first_name,
        orders_alias.last_name,
        orders_alias.country,
        orders_alias.city,
        orders_alias.phone,
        subquery.c.totalSpent,
        subquery.c.lastOrder
    ).join(orders_alias, orders_alias.id == subquery.c.latest_order_id).order_by(subquery.c.lastOrder.desc()).all()
    
    customers_data = []
    for row in results:
        is_email = "@" in row.id
        email = row.id if is_email else None
        phone = row.phone if row.phone else (row.id if not is_email else None)
        full_name = f"{row.first_name or ''} {row.last_name or ''}".strip()
        
        customers_data.append(schemas.CustomerOut(
            id=row.id, name=full_name or row.id, email=email, phone=phone,
            country=row.country, city=row.city, totalSpent=row.totalSpent, lastOrder=row.lastOrder
        ))
    return customers_data


# ==========================================
# 📰 BLOG SECTION
# ==========================================

@app.post("/blog/categories/", response_model=schemas.BlogCategoryOut)
def create_blog_category(category: schemas.BlogCategoryCreate, db: Session = Depends(get_db)):
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

@app.post("/blog/posts/", response_model=schemas.BlogPostOut)
def create_blog_post(
    title: str = Form(...),
    description: str = Form(...),
    content: str = Form(...),
    category: str = Form(...),
    author: str = Form(...),
    tags: str = Form(...),
    is_published: bool = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_category = db.query(models.BlogCategory).filter(models.BlogCategory.name == category).first()
    if not db_category:
        db_category = models.BlogCategory(name=category)
        db.add(db_category); db.commit(); db.refresh(db_category)
    
    file_extension = os.path.splitext(image.filename)[1]
    unique_filename = f"blog_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIRECTORY, unique_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    
    new_post = models.BlogPost(
        title=title, excerpt=description, author=author, content=content,
        tags=tags, category_id=db_category.id, image_url=f"/static/images/{unique_filename}"
    )
    db.add(new_post); db.commit(); db.refresh(new_post)
    return new_post

@app.get("/blog/posts/", response_model=List[schemas.BlogPostOut])
def read_blog_posts(db: Session = Depends(get_db)):
    return db.query(models.BlogPost).options(joinedload(models.BlogPost.category)).all()

@app.delete("/blog/posts/{post_id}", status_code=204)
def delete_blog_post(post_id: int, db: Session = Depends(get_db)):
    post = db.query(models.BlogPost).filter(models.BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post); db.commit()
    return


# ==========================================
# ⭐ PRODUCT REVIEWS
# ==========================================

@app.post("/products/{product_id}/reviews/", response_model=schemas.ReviewOut)
def create_review(product_id: int, review: schemas.ReviewCreate, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db_review = models.Review(
        product_id=product_id, rating=review.rating, text=review.text,
        user_name=review.user_name, email=review.email, verified=True 
    )
    db.add(db_review); db.commit(); db.refresh(db_review)
    return db_review

@app.get("/products/{product_id}/reviews/", response_model=List[schemas.ReviewOut])
def read_reviews(product_id: int, db: Session = Depends(get_db)):
    return db.query(models.Review)\
        .filter(models.Review.product_id == product_id)\
        .order_by(models.Review.created_at.desc())\
        .all()