#!/usr/bin/env python3

import argparse
import requests


def calculate_luhn(number):
    digits = list(map(int, str(number)))
    odd_sum = sum(digits[-1::-2])
    even_sum = sum([sum(divmod(2 * d, 10)) for d in digits[-2::-2]])
    return odd_sum + even_sum


def calculate_verification_digit(number):
    return (10 - (calculate_luhn(number) % 10)) % 10


def luhn_check(number):
    return calculate_luhn(number) % 10 == 0


def get_card_info(number):
    response = requests.get(f"https://lookup.binlist.net/{number[:8]}")
    if response.status_code == 200:
        return response.json()
    else:
        return response.status_code


def get_status_code_info(status_code):
    response = requests.get("https://status.js.org/codes.json")
    if response.status_code == 200:
        status_codes = response.json()
        status = status_codes.get(status_code)
        return status_codes.get(str(status_code))
    else:
        return None


def getter(dict, value):
    if dict.get(value, "") not in (None, "None", "N/A", ""):
        res = str(dict.get(value, "")).title()
    else:
        return None
    return str(res)


def print_card_info(card_info):
    # e.g. Visa Debit, Prepaid
    scheme = (
        str(card_info.get("scheme", "N/A")).title()
        + " "
        + getter(card_info, "type")
        + (", Prepaid" if getter(card_info, "prepaid") else "")
    )
    # e.g. Chase Bank
    bank = card_info.get("bank", "N/A").get("name", "N/A")
    # United States, USD
    country = (
        card_info.get("country", "N/A").get("name", "N/A")
        + ", "
        + card_info.get("country", "N/A").get("currency", "N/A")
    )
    print(scheme, bank, country, sep="\n")


def main():
    parser = argparse.ArgumentParser(
        description="This script calculates the verification digit for an input number and performs the Luhn verification."
    )
    parser.add_argument(
        "-c",
        "--calculate",
        action="store_true",
        help="calculate the verification digit and append it to the number before verifying",
    )
    parser.add_argument(
        "-d",
        "--details",
        action="store_true",
        help="Get issuer details like bank and card type.",
    )
    args = parser.parse_args()

    number = input("Enter a number: ")

    if args.calculate:
        verification_digit = calculate_verification_digit(number)
        print(f"The verification digit is {verification_digit}.")
        number = str(number) + str(verification_digit)

    # Perform Luhn check regardless of details flag
    if luhn_check(number):
        print("--- Number is formally valid according to Luhn algorithm. ---")

    if args.details:  # Call API only if details flag is present
        card_info = get_card_info(number)
        if isinstance(card_info, dict):
            print("- Card details:")
            print_card_info(card_info)
        else:
            status_code_info = get_status_code_info(card_info)
            print(f"Status {card_info}: {status_code_info['message']}")


if __name__ == "__main__":
    main()
