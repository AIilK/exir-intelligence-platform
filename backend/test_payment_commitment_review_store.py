from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.payment_commitment_review_store import (
    PaymentCommitmentReviewStore,
)


class PaymentCommitmentReviewStoreTests(unittest.TestCase):
    def test_decision_is_persisted_and_can_be_reset(self):
        with TemporaryDirectory() as temp_dir:
            store = PaymentCommitmentReviewStore(
                Path(temp_dir) / "reviews.json"
            )
            saved = store.set(
                installment_id=501,
                payment_order_id=9455,
                decision="still_due",
                note="تأیید خزانه",
            )
            self.assertEqual(saved["decision"], "still_due")
            self.assertEqual(store.all()[501]["note"], "تأیید خزانه")

            store.set(
                installment_id=501,
                payment_order_id=9455,
                decision="pending_review",
            )
            self.assertEqual(store.all()[501]["decision"], "pending_review")

    def test_unknown_decision_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            store = PaymentCommitmentReviewStore(
                Path(temp_dir) / "reviews.json"
            )
            with self.assertRaises(ValueError):
                store.set(
                    installment_id=1,
                    payment_order_id=2,
                    decision="unknown",
                )


if __name__ == "__main__":
    unittest.main()
