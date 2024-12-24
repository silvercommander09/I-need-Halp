from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
from flask_socketio import SocketIO, emit

app = Flask(__name__)

app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirect unauthorized users to login

socketio = SocketIO(app)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcement.id'), nullable=False)
    announcement = db.relationship('Announcement', back_populates='comments')

class Announcement(db.Model):
    _tablename_ = 'announcement'
    _table_args_ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    visibility = db.Column(db.String(10), default='public')
    posted_by = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    comments = db.relationship('Comment', back_populates='announcement', lazy=True)

    # Relationship with the User model
    user = db.relationship('User', backref='announcements')

    def __init__(self, title, content, posted_by, user_id, visibility='public'):
        self.title = title
        self.content = content
        self.posted_by = posted_by
        self.user_id = user_id
        self.visibility = visibility

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)

# Poll model
class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False)
    option1 = db.Column(db.String(100), nullable=False)
    option2 = db.Column(db.String(100), nullable=False)
    option1_votes = db.Column(db.Integer, default=0)
    option2_votes = db.Column(db.Integer, default=0)

    def __init__(self, question, option1, option2):
        self.question = question
        self.option1 = option1
        self.option2 = option2

# Vote model
class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    vote = db.Column(db.String(100), nullable=False)  # Store the option they voted for
    user = db.relationship('User', backref='votes')
    poll = db.relationship('Poll', backref='votes')

# Load user for login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Custom role-based decorators
def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                flash("Unauthorized access!", "danger")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for(f"{user.role}_dashboard"))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/update-password', methods=['POST'])
def update_password():
    # Logic to handle password change
    current_password = request.form['current_password']  # noqa: F841
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if new_password != confirm_password:
        flash("Passwords do not match!")
        return redirect(url_for('account'))
    
    # Handle password update here (e.g., verify current password, update the database)
    
    flash("Password updated successfully!")
    return redirect(url_for('account'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/view_reports')
@login_required
@role_required('admin')
def view_reports():
    return render_template('view_reports.html')

@app.route('/settings')
@login_required
@role_required('admin')
def settings():
    return render_template('settings.html')

@app.route('/home')
@login_required
def home():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif current_user.role == 'student':
        return redirect(url_for('student_dashboard'))
    else:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('login'))

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)

@app.route('/admin/manage_users')
@login_required
@role_required('admin')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/view_user/<int:user_id>', methods=['POST', 'GET'])
def view_user(user_id):
    user = User.query.get_or_404(user_id)  # This will return a 404 if the user does not exist.

    if request.method == 'POST':
        # Get updated user details from the form
        user.username = request.form['username']  # Update other fields as necessary
        user.student_id = request.form['student_id']
        user.password = request.form['password']  # Update password or other fields as needed
        
        # Commit changes to the database
        db.session.commit()

        flash('User details updated successfully!', 'success')
        return redirect(url_for("manage_users"))
    
    if request.method == 'POST':
        # Get updated user details from the form
     
        
        user.student_id = request.form['student_id']
        user.year = request.form['year']
        user.section = request.form['section']
        user.password = request.form['password']

        # Commit changes to the database
        db.session.commit()
    return render_template("view_users.html", user=user)

    

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))

# Add User Route
@app.route('/add-user', methods=['POST'])
def add_user():
    # Logic for adding a user
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    
    # Add the user to the database
    new_user = User(username=username, password=password, role=role)
    db.session.add(new_user)
    db.session.commit()

    flash("User added successfully!")
    return redirect(url_for('manage_users'))

@app.route('/manage_elections')
def manage_elections():
    return render_template('manage_elections.html')

@app.route('/manage_ecommerce')
def manage_ecommerce():
    return render_template('manage_ecommerce.html')

@app.route('/manage_forums')
def manage_forums():
    return render_template('manage_forums.html')

@app.route('/post_announcement', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def post_announcement():
    announcements = Announcement.query.order_by(Announcement.timestamp.desc()).all()

    if request.method == 'POST':
        title = request.form['announcement_title']
        content = request.form['announcement_content']
        visibility = request.form.get('visibility', 'public')

        new_announcement = Announcement(
            title=title,
            content=content,
            posted_by=current_user.username,
            user_id=current_user.id,
            visibility=visibility
        )

        db.session.add(new_announcement)
        db.session.commit()

        flash('Announcement posted successfully!', 'success')
        return redirect(url_for('post_announcement'))

    return render_template('post_announcement.html', announcements=announcements)

@app.route('/delete_announcement/<int:announcement_id>', methods=['POST'])
def delete_announcement(announcement_id):
    # Retrieve the announcement to delete
    announcement = Announcement.query.get(announcement_id)
    if announcement:
        # Delete all related comments first
        comments = Comment.query.filter_by(announcement_id=announcement_id).all()
        for comment in comments:
            db.session.delete(comment)
        db.session.commit()
        # Then delete the announcement
        db.session.delete(announcement)
        db.session.commit()
        flash('Announcement and related comments deleted successfully!', 'success')
    else:
        flash('Announcement not found!', 'danger')
    return redirect(url_for('home'))

@app.route('/change_visibility/<int:announcement_id>', methods=['POST'])
@login_required
def change_visibility(announcement_id):
    if current_user.role == 'admin':
        announcement = Announcement.query.get(announcement_id)
        if announcement:
            new_visibility = request.form['visibility']
            announcement.visibility = new_visibility
            db.session.commit()
            flash(f'Visibility changed to {new_visibility}!', 'success')
        else:
            flash('Announcement not found.', 'danger')
    else:
        flash('You do not have permission to change the visibility.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/comment/<int:announcement_id>', methods=['POST'])
def comment(announcement_id):
    content = request.form['comment_content']
    # Ensure the announcement exists before associating with a comment
    announcement = Announcement.query.get(announcement_id)
    
    if announcement:
        # Create the comment and associate it with the announcement
        new_comment = Comment(content=content, announcement_id=announcement.id)
        db.session.add(new_comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')
    else:
        flash('Announcement not found!', 'danger')
    return redirect(url_for('post_announcement'))

@app.route('/student_dashboard')
@login_required
def student_dashboard():
    announcements = Announcement.query.filter_by(visibility='public').all()
    return render_template('student_dashboard.html', announcements=announcements)

@app.route('/student/election', methods=['GET', 'POST'])
@login_required
@role_required('student')
def election():
    poll = Poll.query.first()

    if poll is None:
        flash("No polls available at the moment.", "danger")
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        user_vote = request.form['vote']
        existing_vote = Vote.query.filter_by(user_id=current_user.id, poll_id=poll.id).first()

        if existing_vote:
            flash("You have already voted!", 'danger')
        else:
            new_vote = Vote(user_id=current_user.id, poll_id=poll.id, vote=user_vote)
            db.session.add(new_vote)
            if user_vote == poll.option1:
                poll.option1_votes += 1
            else:
                poll.option2_votes += 1
            db.session.commit()
            flash("Your vote has been recorded.", 'success')

    return render_template('election.html', poll=poll)

@app.route('/student/ecommerce')
@login_required
@role_required('student')
def ecommerce():
    return render_template('ecommerce.html')

@app.route('/student/account')
@login_required
@role_required('student')
def account():
    return render_template('account.html')

@app.route('/forums')
@login_required
def forums():
    return render_template('forums.html')

@app.route('/election_results')
def election_results():
    poll = Poll.query.first()
    return render_template('election_results.html', poll=poll)

@socketio.on('get_poll_results')
def handle_poll_results():
    poll = Poll.query.first()
    emit('poll_results', {
        'option1_votes': poll.option1_votes,
        'option2_votes': poll.option2_votes
    })

if __name__ == '__main__':

    with app.app_context():
        db.create_all()

        poll = Poll.query.first()
        if not poll:
            new_poll = Poll(
                question="Which option do you prefer?",
                option1="Option A",
                option2="Option B"
            )
            db.session.add(new_poll)
            db.session.commit()
            print("Poll created!")

    socketio.run(app, debug=True,allow_unsafe_werkzeug=True)