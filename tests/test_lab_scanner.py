import argparse
import unittest

from scanner import lab_scanner


class ScannerValidationTests(unittest.TestCase):
    def test_private_target_allowed(self):
        self.assertEqual(str(lab_scanner.private_target("192.168.56.20")), "192.168.56.20")

    def test_public_target_blocked(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            lab_scanner.private_target("8.8.8.8")

    def test_port_ranges(self):
        self.assertEqual(lab_scanner.parse_ports("22,80-82,80"), [22, 80, 81, 82])

    def test_large_range_blocked(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            lab_scanner.parse_ports("1-5000")

    def test_ssh_user_allowed(self):
        self.assertEqual(lab_scanner.ssh_user("lab-user"), "lab-user")

    def test_ssh_user_shell_characters_blocked(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            lab_scanner.ssh_user("user;whoami")


if __name__ == "__main__":
    unittest.main()
