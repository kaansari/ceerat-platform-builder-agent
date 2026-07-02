import unittest

from ceerat_builder.main import _domain_key


class DomainKeyTests(unittest.TestCase):
    def test_commerce_aliases(self) -> None:
        requests = [
            "tax shipping coupon checkout customer addresses",
            "add state tax rules",
            "update shipping choices",
            "validate a coupon at checkout",
            "order pricing changes",
            "customer billing address",
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertEqual(_domain_key(request), "commerce")

    def test_unrelated_domain_is_unchanged(self) -> None:
        self.assertEqual(_domain_key("create invoice service"), "invoice")


if __name__ == "__main__":
    unittest.main()
