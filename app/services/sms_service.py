import httpx
import logging
from app.config import get_settings
logger = logging.getLogger("egg_cashback")
settings = get_settings()
class SMSService:
    @staticmethod
    def send_otp(phone_number: str, otp_code: str) -> bool:
        """
        Sends an OTP using the 2Factor SMS API.
        """
        if not settings.SMS_API_KEY:
            logger.warning("SMS_API_KEY (2FACTOR) is not set in environment. Skipping real SMS.")
            return False
            
        url = f"https://2factor.in/API/V1/{settings.SMS_API_KEY}/SMS/{phone_number}/{otp_code}"
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url)
                response.raise_for_status()
                data = response.json()
                
                if data.get("Status") == "Success":
                    logger.info(f"Successfully sent OTP to {phone_number} via 2Factor.")
                    return True
                else:
                    logger.error(f"2Factor API Error: {data}")
                    return False
        except httpx.RequestError as e:
            logger.error(f"Network error while sending SMS OTP: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send SMS OTP: {e}")
            return False