# pdf_generator.py
import sys
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet
import os
from dotenv import load_dotenv
from machine_config import machines_list

def generate_daily_pdf(date_str, output_path):

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

    TARGET_DATE = date_str
    OUTPUT_FILE = output_path

    # --- UTILS ---
    def format_duration(seconds):
        seconds = int(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def format_percentage(value):
        return f"{value:.2f}%"

    # --- LOAD AND PREPARE DATA ---
    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql_query("SELECT * FROM machine_log", conn)
    conn.close()
    df['start_timestamp'] = pd.to_datetime(df['start_timestamp'])
    df['end_timestamp'] = pd.to_datetime(df['end_timestamp'])

    df = df[df['end_timestamp'].notna()]

    # Duration
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

    # Filter for specific date
    df = df[df['start_timestamp'].dt.date == pd.to_datetime(TARGET_DATE).date()]
    # --- INSERT DOWNTIME EVENTS ---
    def insert_downtime(group, date):
        group = group.sort_values('start_timestamp').reset_index(drop=True)
        all_downtime_rows = []

        day_start = datetime.combine(date, datetime.min.time()) + timedelta(hours=6)
        day_end = datetime.combine(date, datetime.min.time()) + timedelta(hours=18)

        # Get jobs that overlap with the 6AM–6PM window
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
        
        result = pd.concat([
            group, 
            pd.DataFrame(all_downtime_rows)
        ], ignore_index=True).sort_values('start_timestamp').reset_index(drop=True)

        return result

    df_list = []
    for machine, group in df.groupby('machine_name'):
        df_list.append(insert_downtime(group, pd.to_datetime(TARGET_DATE)))

    df = pd.concat(df_list).sort_values(by=['machine_name', 'start_timestamp']).reset_index(drop=True)

    # --- REPORT SETUP ---
    styles = getSampleStyleSheet()
    report = []
    doc = SimpleDocTemplate(OUTPUT_FILE, pagesize=A4)

    # Title
    title = Paragraph(f"<b>CNC Machine Daily Report</b><br/>{TARGET_DATE}", styles['Title'])
    report.append(title)
    report.append(Spacer(1, 24))

    # --- SUMMARY PAGE ---
    summary_data = [['Machine', 'Total Runs', 'Total Runtime (HH:MM:SS)', 'Total Downtime (HH:MM:SS)', 'Efficiency Rate (%)']]
    for machine in df['machine_name'].unique():
        machine_df = df[df['machine_name'] == machine]
        machine_uptime = next((m for m in machines_list if m['Machine'] == machine), None)['Uptime']
        total_runtime = machine_df[machine_df['program'].str.contains('DOWNTIME') == False]['duration_seconds'].sum()
        total_downtime = machine_uptime - total_runtime
        if total_downtime < 0:
            total_downtime = 0
        efficiency_rate = (total_runtime / (total_runtime + total_downtime)) * 100 if (total_runtime + total_downtime) > 0 else 0
        run_count = len(machine_df[machine_df['program'].str.contains('DOWNTIME') == False])
        summary_data.append([
            machine,
            run_count,
            format_duration(total_runtime),
            format_duration(total_downtime),
            format_percentage(efficiency_rate)
        ])

    summary_data_machines = {machine[0] for machine in summary_data}

    for machine in machines_list:
        if machine['Machine'] not in summary_data_machines:
            if machine['Uptime'] == 28800:
                uptime = '08:00:00'
            elif machine['Uptime'] == 43200:
                uptime = '12:00:00'
            summary_data.append([
                machine['Machine'],
                0,
                '00:00:00',
                uptime,
                '0.00%'
            ])
        

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

    def remove_outliers_iqr(series):
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        return series[(series >= q1 - 1.5 * iqr) & (series <= q3 + 1.5 * iqr)]

    # --- PER-MACHINE SECTIONS ---
    for machine in df['machine_name'].unique():
        runs = df[df['machine_name'] == machine].copy()
        run_count = len(runs[runs['program'].str.contains('DOWNTIME') == False])
        machine_uptime = next((m for m in machines_list if m['Machine'] == machine), None)['Uptime']
        total_runtime = runs[runs['program'].str.contains('DOWNTIME') == False]['duration_seconds'].sum()
        total_downtime = machine_uptime - total_runtime
        if total_downtime < 0:
            total_downtime = 0
        efficiency_rate = (total_runtime / (total_runtime + total_downtime)) * 100 if (total_runtime + total_downtime) > 0 else 0
        formatted_total = format_duration(total_runtime)

        # Section Header
        header = Paragraph(
            f"<b>Machine: {machine}</b> - Total Run Time: {formatted_total} - Total Runs: {run_count} \nEfficiency: {format_percentage(efficiency_rate)}",
            styles['Heading2']
        )
        report.append(header)
        report.append(Spacer(1, 6))

        # Filter out 'DOWNTIME' entries
        actual_runs = runs[runs['program'].str.contains('DOWNTIME') == False]

        def cut_program_name(program):
            if len(program) > 30:
                return '...' + program[-30:]
            return program

        program_table_data = [['Program', 'Run Count', 'Total Runtime (HH:MM:SS)', 'Avg Cycle Time (Excl. Outliers)']]
        for program_name, group in actual_runs.groupby('program'):
            run_count = len(group)
            total_runtime = group['duration_seconds'].sum()
            duration_formatted = format_duration(total_runtime)

            # Filter outliers and compute average
            filtered_durations = remove_outliers_iqr(group['duration_seconds'])
            avg_cycle = format_duration(filtered_durations.mean()) if not filtered_durations.empty else 'N/A'

            program_table_data.append([cut_program_name(program_name), run_count, duration_formatted, avg_cycle])


        program_table = Table(program_table_data, hAlign='CENTER')
        program_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke if i % 2 else colors.white)
        for i in range(1, len(program_table_data))]
        ]))
        report.append(Spacer(1, 6))
        report.append(Paragraph("<b>Runtime Per Program</b>", styles['Heading3']))
        report.append(program_table)
        report.append(Spacer(1, 12))

        # Table of Runs
        table_data = [['Program', 'Start Time', 'End Time', 'Duration (HH:MM:SS)']]
        for _, row in runs.iterrows():
            table_data.append([
                row['program'],
                row['start_timestamp'].strftime("%H:%M:%S"),
                row['end_timestamp'].strftime("%H:%M:%S"),
                format_duration(row['duration_seconds'])
            ])

        run_table = Table(table_data, repeatRows=1)
        run_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (3, 1), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        *[('BACKGROUND', (0, i), (-1, i), colors.whitesmoke if i % 2 else colors.white)
        for i in range(1, len(table_data))]
        ]))
        report.append(run_table)
        report.append(PageBreak())

    # --- BUILD PDF ---
    doc.build(report)
"""
if __name__ == '__main__':
    date_input = sys.argv[1]
    output_path = sys.argv[2]
    generate_pdf(date_input, output_path)
"""
