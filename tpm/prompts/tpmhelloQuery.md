# Fabric Data Agent – TPM Hello Scenario

This file contains predefined queries.
When asked to run a query, execute the SQL query based on the query against the connected Fabric SQL endpoint.
Always format responses using:
- Clear section headers
- Markdown tables for tabular data
- Bullet points for explanation
- Summary section at the end with insights and key findings
Present the results in a markdown table in a presentable format and make it readable.


---

## TPM Hello Queries

### Query 1 – Hello Scenario Success Rate (Last 30 Days)

Description:
Calculate success rate for Hello scenario in the last 30 days.

Assumptions:
- Table name: tpmhello
- Date column: Date
- Success: If Status column is 0, then it is Success. 
- Failure: If Status column is not 0, then it is a Failure.
- Exclude rows that have null or empty values for Success and Failure
- Calculate success rate based on count of Success and Failures
- Display overall success rate and overall failure rate in percentage. 

---

### Query 2 – Top 5 Errors for Hello Scenario in the Last 30 Days

Description:
Return top 5 error codes for Hello scenario in the last 30 days and calculate failure rate.

Assumptions:
- Table name: tpmhello
- Check for the Status Column
- Success: If Status column is 0, then it is Success. 
- Failure: If Status column is not 0, then it is a Failure.
- Display StatusName which indicates the Error Code
- Display failure rate across the top 5 errors seen
- Only include percentage of devices in each of the error buckets.


---

### Query 3 – List the top 5 device models where Hello failure is seen in the last 30 days

Description:
Return top 5 OEMModel where Hello failure is seen for last 30 days

Assumptions:
- Table name: tpmhello
- Check for the Status Column
- Success: If Status column is 0, then it is Success. 
- Failure: If Status column is not 0, then it is a Failure.
- Display top 5 OEMModel where failure is seen.
- Exclude OEMModel if field is empty or null or not specified.
- Display the top 5 OEMModel with the failure rate of devices in percentage

---