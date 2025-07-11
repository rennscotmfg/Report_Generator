import psycopg2
import pandas as pd
from datetime import timedelta
from cycle_times_gaps import get_gaps
from dotenv import load_dotenv
import os

def connect_to_database():
    load_dotenv()
    db_name = os.getenv('DBNAME')
    db_user = os.getenv('USER')
    db_password = os.getenv('PASSWORD')
    db_host = os.getenv('HOST')
    db_port = os.getenv('PORT')
    # --- CONFIGURATION ---
    DB_CONFIG = {
        'dbname': db_name,
        'user': db_user,
        'password': db_password,
        'host': db_host,
        'port': db_port
    }
    conn = psycopg2.connect(**DB_CONFIG)
    df_untouched = pd.read_sql_query("SELECT * FROM machine_log", conn)
    conn.close()
    return df_untouched

# Function to remove outliers using IQR
def remove_outliers(group):
    Q1 = group['duration_seconds'].quantile(0.25)
    Q3 = group['duration_seconds'].quantile(0.75)
    IQR = Q3 - Q1
    return group[(group['duration_seconds'] >= Q1 - 1.5 * IQR) & (group['duration_seconds'] <= Q3 + 1.5 * IQR)]

def format_duration(seconds):
    td = timedelta(seconds=int(float((seconds))))
    return str(td)

def get_cycle_times():
    df_untouched = connect_to_database()
    df = df_untouched
    df['start_timestamp'] = pd.to_datetime(df['start_timestamp'])
    df['end_timestamp'] = pd.to_datetime(df['end_timestamp'])

    # Calculate duration in minutes
    df['duration_seconds'] = (df['end_timestamp'] - df['start_timestamp']).dt.total_seconds()

    # Optional: Clean up program names (e.g., trim, normalize)
    df['program_clean'] = df['program'].str.strip()
    df = df[df['duration_seconds'] > 60]  # Remove rows with non-positive durations

    # Group by program and remove outliers
    filtered_df = df.groupby('program_clean', group_keys=False).apply(remove_outliers)

    # Calculate average duration per program
    average_durations = (
        filtered_df
        .groupby('program_clean')
        .agg({
            'duration_seconds': 'mean',
            'machine_name': 'first'  # or use 'min', 'max', etc., depending on your case
        })
        .reset_index()
    )

    # Sort by longest average duration
    average_durations = average_durations.sort_values(by='duration_seconds', ascending=False)

    average_durations['formatted_duration'] = average_durations['duration_seconds'].apply(format_duration)

    avg_gaps_df = get_gaps(df_untouched)

    # Merge on machine_name and program/program_clean
    merged_df = average_durations.merge(
        avg_gaps_df,
        how='left',
        left_on=['machine_name', 'program_clean'],
        right_on=['machine_name', 'program']
    )

    # Drop the duplicate 'program' column if you don't need it
    merged_df = merged_df.drop(columns='program')

    merged_df.fillna(' ', inplace=True)


    html = merged_df[['machine_name', 'program_clean', 'formatted_duration', 'avg_gap']].to_html(index=False, table_id='table')
    
    return html
