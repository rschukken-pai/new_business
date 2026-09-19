from google.cloud import bigquery
import credentials

GCP_Project = credentials.GCP_PROJECT
GCP_Dataset = GCP_Project + "." + credentials.GCP_DATASET


def new_business(patient_id, business):
    patient_id = int(patient_id)  # cast to int, matching the column's INT64 type
    business = int(business)      # cast to int, matching the column's INT64 type

    client = bigquery.Client(GCP_Project)
    new_business_view = "new_business"

    query = f"""
        SELECT * FROM `{GCP_Dataset}.{new_business_view}`
        WHERE patient = @patient_id
        AND business = @business
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patient_id", "INT64", patient_id),
            bigquery.ScalarQueryParameter("business", "INT64", business),
        ]
    )

    query_job = client.query(query, job_config=job_config)
    results = query_job.result()

    rows_list = [dict(row) for row in results]

    return rows_list