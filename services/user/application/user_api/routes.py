from flask import jsonify, make_response, request
from shop_common.auth import bearer_token
from sqlalchemy.exc import IntegrityError

from . import user_api_blueprint
from .. import db, tokens
from ..models import User
from ..schemas import RegisterRequest, LoginRequest
from ..validation import validate_form


def _user_from_token() -> User | None:
    """Stateless (pattern 10): who you are comes from the signed token, not a server session."""
    token = bearer_token(request.headers.get("Authorization"))
    claims = tokens.decode(token) if token else None
    return db.session.get(User, int(claims["sub"])) if claims else None


@user_api_blueprint.route("/api/users", methods=["GET"])
def get_users():
    return jsonify([u.to_json() for u in User.query.all()])


@user_api_blueprint.route("/api/user/create", methods=["POST"])
def post_register():
    data, error = validate_form(RegisterRequest, request.form)
    if error:
        return error

    user = User(
        username=data.username,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        password=data.password,
    )
    user.encode_password()
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return make_response(
            jsonify({"message": "Username or email is already taken"}), 409
        )
    return jsonify({"message": "User added", "result": user.to_json()})


@user_api_blueprint.route("/api/user/login", methods=["POST"])
def post_login():
    data, error = validate_form(LoginRequest, request.form)
    if error:
        return error

    user = User.query.filter_by(username=data.username).first()
    if user and user.verify_password(data.password):
        # Nothing is written to the database or a session: the token itself is the proof.
        return jsonify({"message": "Logged in", "token": tokens.issue(user), "expires_in": int(tokens.TOKEN_LIFETIME.total_seconds())})
    return make_response(jsonify({"message": "Not logged in"}), 401)


@user_api_blueprint.route("/api/user/logout", methods=["POST"])
def post_logout():
    # No server-side session to end. The browser deletes its token; it also expires within an hour.
    return jsonify({"message": "Logged out. Tokens are not stored on the server, so the browser just forgets it."})


@user_api_blueprint.route("/api/user/public-key", methods=["GET"])
def get_public_key():
    """Other services verify tokens with this key. It is public: it can check, not sign."""
    return jsonify({"algorithm": "RS256", "public_key_pem": tokens.public_key_pem()})


@user_api_blueprint.route("/api/user/<username>/exists", methods=["GET"])
def get_username(username):
    if User.query.filter_by(username=username).first() is not None:
        return jsonify({"result": True})
    return make_response(jsonify({"message": "Cannot find username"}), 404)


@user_api_blueprint.route("/api/user", methods=["GET"])
def get_user():
    user = _user_from_token()
    if user is None:
        return make_response(jsonify({"message": "Not logged in"}), 401)
    return jsonify({"result": user.to_json()})
