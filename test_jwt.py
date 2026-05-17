from jose import jwt
token = jwt.encode({"email": "test"}, "G26X1QcTgt0mKoCT7YdAYNv9v7+WGqlA/wZvHIZjTI=", algorithm="HS256")
print("PY Token:", token)
