import argparse


def calculate_verification_digit(number):
    digits = list(map(int, str(number)))
    odd_sum = sum(digits[-1::-2])
    even_sum = sum([sum(divmod(2 * d, 10)) for d in digits[-2::-2]])
    return (10 - ((odd_sum + even_sum) % 10)) % 10


def luhn_check(number):
    digits = list(map(int, str(number)))
    odd_sum = sum(digits[-1::-2])
    even_sum = sum([sum(divmod(2 * d, 10)) for d in digits[-2::-2]])
    return (odd_sum + even_sum) % 10 == 0


parser = argparse.ArgumentParser(
    description="This script calculates the verification digit for an input number and performs the Luhn verification."
)
parser.add_argument(
    "-c",
    "--calculate",
    action="store_true",
    help="calculate the verification digit and append it to the number before verifying",
)
args = parser.parse_args()

number = input("Enter a number: ")

if args.calculate:
    verification_digit = calculate_verification_digit(number)
    print(f"The verification digit is {verification_digit}. Appending to input number.")
    number = str(number) + str(verification_digit)

if luhn_check(number):
    print("The number is valid according to the Luhn algorithm.")
else:
    print("The number is not valid according to the Luhn algorithm.")
