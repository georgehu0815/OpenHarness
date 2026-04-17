
# Fabric Data Agent - TPM Attestation Status

## TPM Attestation Status Queries

Description:
How many TPMs are Attestable, Possibly attestable and Cannot be Attested state? Show me the device distribution. Which top 3 TPMs cannot be attested?

Assumptions:
- Table Name: tpmhealthcheck
- Check for HealthStatus column which has values "Attestable", "Possibly attestable" and "Cannot be attested" 
- Device column: device_id
- Show the distribution of devices by count and percentage by HealthStatus column
- Check for TpmManufacturerName and find the top 3 ones for the TPMs that are in "Cannot be Attested" state


---