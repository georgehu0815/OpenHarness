# Fabric Data Agent - TPM Clear Reasons 

## TPM Clear Queries

Description:
What are the top 3 TPM Clear reasons, show the device distribution and in which top 3 TPM Manufacturers are showing the clear?

Assumptions:
- Table Name: tpmclear
- Check prov_data_reason column and show the top 3 prov_data_reason by count of devices. Use prov_device_id for this.
- Also check drv_data_requester column and show the top 3 drv_data_requester by count of devices. use drv_device_id for this
- In addition to device count, also include percentage of devices for each bucket.

---