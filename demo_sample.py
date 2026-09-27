def get_user_profile(user_data: dict, user_id: str):
    # Missing null safety checks and raw SQL concatenation
    username = user_data["profile"]["username"]
    query = f"SELECT * FROM users WHERE id = '{user_id}' AND name = '{username}'"
    return query
