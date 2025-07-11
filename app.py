from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import os
from daily_pdf_generator import generate_daily_pdf
from nightly_pdf_generator import generate_nightly_pdf
from weekly_pdf_generator import generate_weekly_pdf
from cycle_times import get_cycle_times

app = Flask(__name__)
UPLOAD_FOLDER = 'static/pdf'
CYCLE_TIME_PATH = 'static/html/cycle_time_table.html'
CYCLE_TIME_FOLDER = 'static/html'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CYCLE_TIME_PATH'] = CYCLE_TIME_PATH
app.config['CYCLE_TIME_FOLDER'] = CYCLE_TIME_FOLDER

# Route to list and download files
@app.route('/files')
def list_files():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('files.html', files=files)

@app.route('/open/<filename>')
def open_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    return redirect(url_for('list_files'))

# Route with date picker
@app.route('/')
def home():
    return redirect('/generate')
@app.route('/generate')
def generate():
    return render_template('generate.html')
@app.route('/generate/daily', methods=['GET', 'POST'])
def generate_daily():
    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            # Call your script with the selected date
            output_filename = f"daily_report_{selected_date}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            generate_daily_pdf(selected_date, output_path)
            
            # After generation, serve the file
            return redirect(url_for('list_files'))
    return render_template('generate_daily.html')

@app.route('/generate/weekly', methods=['GET', 'POST'])
def generate_weekly():
    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            # Call your script with the selected date
            output_filename = f"weekly_report_{selected_date}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            generate_weekly_pdf(selected_date, output_path)
            
            # After generation, serve the file
            return redirect(url_for('list_files'))
    return render_template('generate_weekly.html')

@app.route('/generate/nightly', methods=['GET', 'POST'])
def generate_noon():
    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            # Call your script with the selected date
            output_filename = f"noon_report_{selected_date}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            generate_nightly_pdf(selected_date, output_path)
            
            # After generation, serve the file
            return redirect(url_for('list_files'))
    return render_template('generate_nightly.html')

@app.route('/generate/cycle-times')
def generate_cycle_times():
    if not os.path.exists(app.config['CYCLE_TIME_FOLDER']):
        os.makedirs(app.config['CYCLE_TIME_FOLDER'])
    html = get_cycle_times()
    with open(app.config['CYCLE_TIME_PATH'], 'w')as f:
        f.write(html)
    return redirect(url_for('cycle_times'))

@app.route('/cycle-times')
def cycle_times():
    cycle_times = 'Something went wrong'
    if os.path.exists(app.config['CYCLE_TIME_PATH']):
        with open(app.config['CYCLE_TIME_PATH'], 'r') as f:
            cycle_times = f.read()
    else:
        return redirect(url_for('generate_cycle_times'))
    return render_template('cycle_times.html', cycle_times=cycle_times)

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host='0.0.0.0', debug=False)
