import argparse

def calculate_luhn(number):
    digits = list(map(int, str(number)))
    odd_sum = sum(digits[-1::-2])
    even_sum = sum([sum(divmod(2 * d, 10)) for d in digits[-2::-2]])
    return (odd_sum + even_sum)

def calculate_verification_digit(number):
    return (10 - (calculate_luhn(number) % 10)) % 10

def luhn_check(number):
    return calculate_luhn(number) % 10 == 0

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
    print(f"The verification digit is {verification_digit}.")
    number = str(number) + str(verification_digit)

if luhn_check(number):
    print("The number is valid according to the Luhn algorithm.")
else:
    print("The number is not valid according to the Luhn algorithm.")
