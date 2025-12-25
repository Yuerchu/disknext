from pydantic import BaseModel

class CaptchaRequestBase(BaseModel):
    token: str
    secret: str