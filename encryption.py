# Import necessary modules from pycryptodome
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP

# This module converts binary data to hexadecimal
from binascii import hexlify

# Step 2: Generate new RSA key
# Create an RSA key pair with a key size of 1024 bits
key = RSA.generate(1024)

# Set the private_key variable to the generated key
private_key = key
print("Private key: ", private_key)
# Derive the public key from the generated key
public_key = key.publickey()

print("Public Key: ", public_key)
plateNumber = b'B340TYS'
cipher_rsa = PKCS1_OAEP.new(public_key)
encryptedPlate = cipher_rsa.encrypt(plateNumber)

print("Plate: ", plateNumber)
print("Encrypted Plate: ", hexlify(encryptedPlate))

cipher_rsa = PKCS1_OAEP.new(private_key)
decryptedPlate = cipher_rsa.decrypt(encryptedPlate)

print("Decrypted Plate: ", decryptedPlate)