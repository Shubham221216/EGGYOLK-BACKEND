import io
import base64
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from app.config import get_settings

settings = get_settings()


class QRService:
    @staticmethod
    def generate_campaign_qr_png(destination_url: str = None) -> bytes:
        """Generates high-resolution PNG bytes for printing packaging QR."""
        target_url = destination_url or settings.FRONTEND_BASE_URL

        qr = qrcode.QRCode(
            version=2,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12,
            border=3,
        )
        qr.add_data(target_url)
        qr.make(fit=True)

        # Create styled QR image with warm egg/amber palette
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=SolidFillColorMask(
                back_color=(255, 255, 255),
                front_color=(20, 20, 20)
            )
        )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer.getvalue()

    @staticmethod
    def generate_campaign_qr_base64(destination_url: str = None) -> str:
        """Returns Data URL string of QR code for direct frontend display."""
        png_bytes = QRService.generate_campaign_qr_png(destination_url)
        encoded = base64.b64encode(png_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
