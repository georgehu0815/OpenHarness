# Fabric Data Agent - TPM State Changes

## Instructions
This file contains predefined queries.
When asked to run a query, execute the SQL query based on the query against the connected Fabric SQL endpoint.
Table Name: tpmstatechangedsincelastrun
- To check if OS Build has changed, check for columns data_currentBuildNumber and data_lastBuildNumber. If they are different then OS Build number has changed, otherwise they are the same. 
- To check if Firmware version has changed, check for columns data_currentFirmwareVersion and data_lastFirmwareVersion. If they are different then firmware version has changed, otherwise they are the same. 
- To check if Manufacturer has changed, check for columns data_currentManufacturerId and data_lastManufacturerId. If they are different then Manufacturer has changed, otherwise they are the same. 

Always format responses using:
- Clear section headers
- Markdown tables for tabular data
- Bullet points for explanation
- Summary section at the end with insights and key findings
- Include Manufacture names in the output instead of Manufacturer Ids.
Present the results in a markdown table in a presentable format and make it readable.

### TPM State Changes Queries

Description:
Show the count of distinct devices that have firmware version changed. List the top 3 TPM Manufacturers based on the result.
Show the count of distinct devices that have manufacturer changed. List the top 3 OEMs based on the result.
Show the count of distinct devices where both manufacturer and firmware version have changed. List the top 3 Device models based on the result.

---