import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet
import sys
import os
from dotenv import load_dotenv
from machine_config import machines_list

def generate_weekly_pdf(date_str, output_path):

    # --- CONFIGURATION ---
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


    # Define workweek range
    START_DATE = pd.to_datetime(date_str)  # Monday
    END_DATE = START_DATE + timedelta(days=6)  # Sunday

    date_range = pd.date_range(start=START_DATE, end=END_DATE)

    OUTPUT_FILE = output_path

    # --- UTILS ---
    def format_duration(seconds):
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def format_percentage(value):
        return f"{value:.2f}%"

    def remove_outliers_iqr(series):
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        return series[(series >= q1 - 1.5 * iqr) & (series <= q3 + 1.5 * iqr)]

    # --- LOAD AND PREPARE DATA ---
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql_query("SELECT * FROM machine_log", conn)
    conn.close()
    df['start_timestamp'] = pd.to_datetime(df['start_timestamp'])
    df['end_timestamp'] = pd.to_datetime(df['end_timestamp'])

    # Filter for the full workweek
    df = df[(df['start_timestamp'].dt.date >= START_DATE.date()) & 
            (df['start_timestamp'].dt.date <= END_DATE.date())]
    df = df[df['end_timestamp'].notna()]

    # Calculate initial durations
    df['duration_seconds'] = (df['end_timestamp'] - df['start_timestamp']).dt.total_seconds().astype(int)

    def split_cross_day_rows(df):
        split_rows = []

        for _, row in df.iterrows():
            start = row['start_timestamp']
            end = row['end_timestamp']

            # If same day, keep it as is
            if start.date() == end.date():
                split_rows.append(row.to_dict())
            else:
                # While the end is past midnight, split at each day
                current_start = start
                while current_start.date() < end.date():
                    midnight = datetime.combine(current_start.date() + timedelta(days=1), datetime.min.time())
                    split_rows.append({
                        **row,
                        'start_timestamp': current_start,
                        'end_timestamp': midnight,
                        'duration_seconds': int((midnight - current_start).total_seconds())
                    })
                    current_start = midnight

                # Final piece
                split_rows.append({
                    **row,
                    'start_timestamp': current_start,
                    'end_timestamp': end,
                    'duration_seconds': int((end - current_start).total_seconds())
                })

        return pd.DataFrame(split_rows)

    df = split_cross_day_rows(df)

    # --- DOWNTIME HANDLING ---

    def insert_downtime(group, date_range):
        group = group.sort_values('start_timestamp').reset_index(drop=True)

        all_downtime_rows = []

        for date in date_range:
            day_start = datetime.combine(date, datetime.min.time()) + timedelta(hours=6)
            day_end = datetime.combine(date, datetime.min.time()) + timedelta(hours=18)

            # Get jobs that overlap with the 6AMâ€“6PM window
            in_window_jobs = group[
                (group['end_timestamp'] > day_start) & 
                (group['start_timestamp'] < day_end)
            ].copy()

            in_window_jobs = in_window_jobs.sort_values('start_timestamp').reset_index(drop=True)
            current_time = day_start

            for _, row in in_window_jobs.iterrows():
                job_start = max(row['start_timestamp'], day_start)
                job_end = min(row['end_timestamp'], day_end)

                if job_start > current_time:
                    # Insert downtime from current_time to job_start
                    downtime_row = {
                        'machine_name': row['machine_name'],
                        'program': 'DOWNTIME',
                        'start_timestamp': current_time,
                        'end_timestamp': job_start,
                        'duration_seconds': int((job_start - current_time).total_seconds())
                    }
                    all_downtime_rows.append(downtime_row)

                current_time = max(current_time, job_end)

            # Insert downtime at end of day if needed
            if current_time < day_end:
                downtime_row = {
                    'machine_name': group.iloc[0]['machine_name'] if not group.empty else '',
                    'program': 'DOWNTIME',
                    'start_timestamp': current_time,
                    'end_timestamp': day_end,
                    'duration_seconds': int((day_end - current_time).total_seconds())
                }
                all_downtime_rows.append(downtime_row)

        # Combine original jobs and downtime
        result = pd.concat([
            group, 
            pd.DataFrame(all_downtime_rows)
        ], ignore_index=True).sort_values('start_timestamp').reset_index(drop=True)

        return result

    # Insert downtime rows per machine
    df_list = []
    for machine, group in df.groupby('machine_name'):
        df_list.append(insert_downtime(group, date_range))

    df = pd.concat(df_list).sort_values(by=['machine_name', 'start_timestamp']).reset_index(drop=True)

    # --- REPORT SETUP ---
    styles = getSampleStyleSheet()
    report = []
    doc = SimpleDocTemplate(OUTPUT_FILE, pagesize=A4)

    # Title with week range
    title = Paragraph(
        f"<b>CNC Machine Weekly Report</b><br/>{START_DATE.date()} to {END_DATE.date()}",
        styles['Title']
    )
    report.append(title)
    report.append(Spacer(1, 24))

    # --- SUMMARY PAGE ---
    summary_data = [['Machine', 'Total Runs', 'Total Runtime', 'Total Downtime', 'Available Hours', 'Efficiency Rate (%)']]
    for machine in df['machine_name'].unique():
        machine_df = df[df['machine_name'] == machine]
        machine_uptime = next((m for m in machines_list if m['Machine'] == machine), None)['Uptime'] * 5
        total_runtime = machine_df[~machine_df['program'].str.contains('DOWNTIME')]['duration_seconds'].sum()
        total_downtime = machine_uptime - total_runtime
        total_downtime= max(total_downtime, 0)  # Ensure non-negative runtime
        efficiency_rate = (total_runtime / (machine_uptime)) * 100 if (total_runtime + total_downtime) > 0 else 0
        run_count = len(machine_df[~machine_df['program'].str.contains('DOWNTIME')])
        summary_data.append([
            machine,
            run_count,
            format_duration(total_runtime),
            format_duration(total_downtime),
            format_duration(machine_uptime),
            format_percentage(efficiency_rate)
        ])

    # Add machines with zero data if missing
    summary_data_machines = {row[0] for row in summary_data[1:]}
    for machine in machines_list:
        if machine['Machine'] not in summary_data_machines:
            uptime = format_duration(machine['Uptime'] * 5)  # 5 days of uptime
            summary_data.append([machine['Machine'], 0, '00:00:00', uptime, uptime, '0.00%'])

    summary_table = Table(summary_data, hAlign='CENTER')
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke if i % 2 else colors.white)
        for i in range(1, len(summary_data))]
    ]))
    report.append(Paragraph("<b>Summary</b>", styles['Heading2']))
    report.append(summary_table)
    report.append(PageBreak())

    # --- DAILY BREAKDOWN PER MACHINE ---
    report.append(Paragraph("<b>Daily Breakdown Per Machine</b>", styles['Heading2']))
    daily_summary_data = [['Machine', 'Date', 'Runtime (HH:MM:SS)', 'Downtime (HH:MM:SS)', 'Efficiency Rate (%)']]

    for machine in df['machine_name'].unique():
        machine_df = df[df['machine_name'] == machine]
        for single_date in pd.date_range(START_DATE, END_DATE):
            day_df = machine_df[machine_df['start_timestamp'].dt.date == single_date.date()]
            machine_uptime = next((m for m in machines_list if m['Machine'] == machine), None)['Uptime']
            total_runtime = day_df[~day_df['program'].str.contains('DOWNTIME')]['duration_seconds'].sum()
            total_downtime = machine_uptime - total_runtime
            total_downtime = max(total_downtime, 0)  # Ensure non-negative downtime
            total = total_runtime + total_downtime
            efficiency = (total_runtime / total) * 100 if total > 0 else 0
            daily_summary_data.append([
                machine,
                single_date.date(),
                format_duration(total_runtime),
                format_duration(total_downtime),
                format_percentage(efficiency)
            ])

    daily_summary_data[1:] = sorted(
        daily_summary_data[1:], 
        key=lambda x: (x[1], x[0])  # x[1] is Date, x[0] is Machine
    )


    daily_summary_table = Table(daily_summary_data, hAlign='CENTER')
    daily_summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke if i % 2 else colors.white)
        for i in range(1, len(daily_summary_data))]
    ]))
    report.append(daily_summary_table)
    report.append(PageBreak())

    # --- PER-MACHINE SECTIONS ---
    for machine in df['machine_name'].unique():
        runs = df[df['machine_name'] == machine].copy()
        run_count = len(runs[~runs['program'].str.contains('DOWNTIME')])
        machine_uptime = next((m for m in machines_list if m['Machine'] == machine), None)['Uptime'] * 5
        total_runtime = runs[~runs['program'].str.contains('DOWNTIME')]['duration_seconds'].sum()
        total_downtime = machine_uptime - total_runtime
        total_downtime = max(total_downtime, 0)  # Ensure non-negative downtime
        efficiency_rate = (total_runtime / (total_runtime + total_downtime)) * 100 if (total_runtime + total_downtime) > 0 else 0
        formatted_total = format_duration(total_runtime)

        header = Paragraph(
            f"<b>Machine: {machine}</b> - Total Run Time: {formatted_total} - Total Runs: {run_count} \nEfficiency: {format_percentage(efficiency_rate)}",
            styles['Heading2']
        )
        report.append(header)
        report.append(Spacer(1, 6))

        actual_runs = runs[~runs['program'].str.contains('DOWNTIME')]

        program_table_data = [['Program', 'Run Count', 'Total Runtime', 'Avg Cycle Time']]
        for program_name, group in actual_runs.groupby('program'):
            run_count_prog = len(group)
            total_runtime_prog = group['duration_seconds'].sum()
            duration_formatted = format_duration(total_runtime_prog)
            avg_cycle_time = format_duration(remove_outliers_iqr(group['duration_seconds']).mean() if len(group) > 1 else group['duration_seconds'].mean())
            program_table_data.append([
                program_name,
                run_count_prog,
                duration_formatted,
                avg_cycle_time
            ])

        program_table = Table(program_table_data, hAlign='CENTER')
        program_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke if i % 2 else colors.white)
        for i in range(1, len(program_table_data))]
        ]))

        report.append(program_table)
        report.append(PageBreak())

    # --- BUILD PDF ---
    doc.build(report)
"""
if __name__ == '__main__':
    date_input = sys.argv[1]
    output_path = sys.argv[2]
    generate_pdf(date_input, output_path)
"""