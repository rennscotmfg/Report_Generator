from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import os
import subprocess

app = Flask(__name__)
UPLOAD_FOLDER = 'static/pdf'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
            
            subprocess.run(['python', 'daily_pdf_generator.py', selected_date, output_path])
            
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
            
            subprocess.run(['python', 'weekly_pdf_generator.py', selected_date, output_path])
            
            # After generation, serve the file
            return redirect(url_for('list_files'))
    return render_template('generate_weekly.html')

@app.route('/generate/noon', methods=['GET', 'POST'])
def generate_noon():
    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            # Call your script with the selected date
            output_filename = f"noon_report_{selected_date}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            subprocess.run(['python', 'noon_pdf_generator.py', selected_date, output_path])
            
            # After generation, serve the file
            return redirect(url_for('list_files'))
    return render_template('generate_noon.html')

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(host='0.0.0.0', debug=False)
