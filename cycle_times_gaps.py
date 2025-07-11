import pandas as pd
from datetime import timedelta


def get_gaps(df):
    # --- Prepare data ---
    df['start_timestamp'] = pd.to_datetime(df['start_timestamp'])
    df['end_timestamp'] = pd.to_datetime(df['end_timestamp'])
    df['start_date'] = df['start_timestamp'].dt.date
    df['program_clean'] = df['program'].str.strip()

    # Calculate duration in seconds
    df['duration_seconds'] = (df['end_timestamp'] - df['start_timestamp']).dt.total_seconds()

    # Remove non-positive or very short durations (e.g., < 60 seconds)
    df = df[df['duration_seconds'] > 60]

    # --- Step 1: Remove duration outliers per program ---

    def remove_outliers_iqr(group, col='duration_seconds'):
        Q1 = group[col].quantile(0.25)
        Q3 = group[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        return group[(group[col] >= lower) & (group[col] <= upper)]

    df = df.groupby('program_clean', group_keys=False).apply(remove_outliers_iqr)

    # --- Step 2: Sort by machine_name and start_timestamp ---

    df = df.sort_values(by=['machine_name', 'start_timestamp']).reset_index(drop=True)

    prev_program = df['program_clean'].shift()
    prev_date = df['start_date'].shift()

    new_group = ((df['program_clean'] != prev_program) | (df['start_date'] != prev_date)).cumsum()

    # Assign the group ID
    df['group_id'] = new_group

    groups = df.groupby('group_id')

    filtered_df = groups.filter(lambda x: len(x) > 1)

    # Sort if needed
    filtered_df = filtered_df.sort_values(['group_id', 'start_timestamp'])

    # Calculate next_start_timestamp per group
    filtered_df['next_start_timestamp'] = filtered_df.groupby('group_id')['start_timestamp'].shift(-1)

    # Calculate gap_seconds
    filtered_df['gap_seconds'] = (filtered_df['next_start_timestamp'] - filtered_df['end_timestamp']).dt.total_seconds()

    # Now you can safely drop NaNs in gap_seconds
    df_clean = filtered_df.dropna(subset=['gap_seconds'])

    # Calculate Q1 and Q3
    Q1 = df_clean['gap_seconds'].quantile(0.25)
    Q3 = df_clean['gap_seconds'].quantile(0.75)
    IQR = Q3 - Q1

    # Define bounds
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR

    # Filter out outliers
    df_no_outliers = df_clean[
        (df_clean['gap_seconds'] >= lower_bound) &
        (df_clean['gap_seconds'] <= upper_bound)
    ]

    def format_duration(seconds):
        td = timedelta(seconds=int(float((seconds))))
        return str(td)

    # Group by program and average
    avg_gaps_df = df_no_outliers.groupby(['program', 'machine_name'])['gap_seconds'].mean().reset_index()
    avg_gaps_df = avg_gaps_df.rename(columns={'gap_seconds': 'avg_gap'})

    avg_gaps_df.sort_values(by='avg_gap', ascending=False, inplace=True)

    avg_gaps_df['avg_gap'] = avg_gaps_df['avg_gap'].apply(format_duration)
    
    avg_gaps_df.fillna(' ')

    avg_gaps_df = avg_gaps_df[['machine_name', 'program', 'avg_gap']]
    
    return avg_gaps_df