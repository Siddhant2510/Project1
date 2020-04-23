import os
import requests

from flask import Flask, session, render_template,request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("books_data"):
    raise RuntimeError("books_data is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("books_data"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/")
def index():
    # Home page
    session.pop('userid',None)
    return render_template("index.html")

@app.route("/Registration", methods=["GET", "POST"])
def registration():
    # Opening registration form
    if request.method=="GET":
        return render_template("registration.html")
    
    # Initialising name to enter in table
    name=request.form.get("Firstname")+" "+request.form.get("Lastname")
    
    # Initialising userid 
    userid=request.form.get("userid")

    # Checking that given userid doesnot exist already
    userids=db.execute("select userid from users").fetchall()
    for uid in userids:
        if f"{uid}"==f"('{userid}',)":
            return render_template("error.html", msg=f"username '{userid}' is not available, try something else")
    
    # Checking User has entered same password both times
    if request.form.get("password")!=request.form.get("checkpassword"):
        return render_template("error.html", msg="Passwords should be similar")
    
    # Initialising password
    password=request.form.get("password")
    
    # Inserting data into table
    db.execute("insert into users (name, userid, password) values(:name, :userid, :password)",
    {"name":name.strip(), "userid":userid.strip(), "password":password.strip()})
    db.commit()
    
    # Taking user to success page
    return render_template("success.html")

@app.route("/Login", methods=["GET", "POST"])
def login():

    # Opening form for login
    if request.method=="GET":
        return render_template("login.html")

    # Initialising userid and password
    userid=request.form.get("userid").strip()
    password=request.form.get("password").strip()
    session["userid"]=userid

    # Checkig if userid exist and entered correct password
    if db.execute("select * from users where userid=:userid and password=:password",{"userid":userid, "password":password}).rowcount==0:
        return render_template("error.html", msg="Username doesnot exist or password is incorrect")
    
    # Taking user to search page
    return render_template("search.html")

@app.route("/Login/books", methods=["POST"])
def search():

    # Initialising data 
    isbn=request.form.get("isbn").strip()
    title=request.form.get("title").strip()
    author=request.form.get("author").strip()

    # Doing this for like clause
    if isbn != '':
        isbn='%'+request.form.get("isbn").strip()+'%'
    if title != '':
        title='%'+request.form.get("title").strip()+'%'
    if author != '':
        author='%'+request.form.get("author").strip()+'%'

    # Passing error if no book found
    if db.execute("select * from books where isbn like :isbn or upper(title) like upper(:title) or upper(author) like upper(:author)", {"isbn":isbn, "title":title, "author":author}).rowcount==0:
        return render_template("error.html", msg="Haven't found the searched book")
    
    # Passing only searched books (Case insensitive)
    books=db.execute("select * from books where isbn like :isbn or upper(title) like upper(:title) or upper(author) like upper(:author)", 
    {"isbn":isbn, "title":title, "author":author}).fetchall()

    #returning selected books
    return render_template("books.html", books=books)

@app.route("/Login/books/<int:book_id>")
def book(book_id):

    if "userid" not in session:
        return render_template("error.html", msg="You need to login to access this page")
    
    # Selecting particular book
    book=db.execute("select * from books where id = :book_id", {"book_id":book_id}).fetchone()

    # Selecting reviews of particular book
    reviews=db.execute("select * from reviews where id = :book_id",{"book_id":book_id}).fetchall()

    # Initialising average rating and reviews count
    av_rating=avg_rating(book_id,book.isbn)
    review_count=rev_count(book_id,book.isbn)
    
    # Returning to show all details
    return render_template("book.html", book=book, review_count=review_count, av_rating=av_rating, reviews=reviews)

@app.route("/Login/books/<int:book_id>/review", methods=["GET", "POST"])
def review(book_id):

    userid=session["userid"]
    
    # Initialising ratings and text reviews
    
    rating=request.form.get("ratings")
    review=request.form.get("review")

    # Pushing ratings and reviews to database
    if review != "" and rating == "":
        return render_template("error.html", msg="Give rating also please")
    if db.execute("select * from reviews where userid=:userid and id=:book_id", {"userid":userid, "book_id":book_id}).rowcount!=0:
        return render_template("error.html", msg="You already submitted review for this book")
    if rating != None and review == "":
        db.execute("insert into reviews (rating, userid, id) values (:rating, :userid, :book_id)",
        {"rating":rating, "userid":userid, "book_id":book_id})
        db.commit()
    if rating != None and review != "":
        db.execute("insert into reviews (rating, review, userid, id) values (:rating, :review, :userid, :book_id)",
        {"rating":rating, "review":review, "userid":userid, "book_id":book_id})
        db.commit()
    return render_template("reviewsub.html",book_id=book_id)


# Route for accessing api
@app.route("/api/<string:isbn>")
def api(isbn):
    book=db.execute("select * from books where isbn=isbn").fetchone()
    review_count=rev_count(book.id,book.isbn)
    av_rating=avg_rating(book.id,book.isbn)
    return jsonify({
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "isbn": book.isbn,
        "review_count": review_count,
        "average_score": av_rating
    })


# Function for calculating review count
def rev_count(book_id,isbn):
    
    # Getting api
    
    res=requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":"8Rj8JFXZxeinrxVBvWyGug", "isbns":isbn})
    
    data=res.json()
    count=db.execute("select count(*) from reviews where id=:book_id",{"book_id":book_id}).fetchall()
    review_count=data["books"][0]["work_ratings_count"]+count[0][0]
    return review_count

# Function for calculating average rating
def avg_rating(book_id,isbn):
    
    # Getting api

    res=requests.get("https://www.goodreads.com/book/review_counts.json", params={"key":"8Rj8JFXZxeinrxVBvWyGug", "isbns":isbn})
    
    data=res.json()
    review_count=rev_count(book_id,isbn)
    api_rating_sum=float(data["books"][0]["average_rating"])*data["books"][0]["work_ratings_count"]

    my_rating_sum=db.execute("select sum(rating) from reviews where id=:book_id",{"book_id":book_id}).fetchall()
    
    if my_rating_sum[0][0] != None:
        avg_rating=(float(api_rating_sum)+float(my_rating_sum[0][0]))/review_count
    else:
        avg_rating=float(data["books"][0]["average_rating"])

    avg_rating=round(avg_rating,2)

    return avg_rating

if __name__ == "__main__":
    main()