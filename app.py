# app.py

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from config import Config
from models import db, SafetyReport, Drug, Patient, Reaction, Company
from flask_caching import Cache
from sqlalchemy.orm import joinedload
from sqlalchemy import func, extract
from collections import defaultdict
import math
from sqlalchemy.orm import aliased
import datetime
import hashlib

# Initialize the Flask application
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
cache = Cache(app)

# Precomputed SHA-256 hash for admin password authentication
ADMIN_PW_HASH = "4813494d137e1631bba301d5acab6e7bb7aa74ce1185d456565ef51d737677b2"

#########################
# HOME PAGE ROUTES
#########################

@app.route('/home')
def home():
    """
    Renders the home page of the application.
    """
    return render_template('home.html')


@app.route('/')
def index():
    """
    Displays a paginated table of safety reports.
    Allows optional filtering by drug name.
    """
    page = int(request.args.get('page', '1'))
    filter_drug = request.args.get('filter_drug', '').strip()
    per_page = 30
    offset_val = (page - 1) * per_page

    # Alias for Patient to facilitate joins
    P = aliased(Patient)

    # Base query with outer join to Patient for demographic details
    q = (db.session.query(SafetyReport, P)
         .outerjoin(P, SafetyReport.safetyreportid == P.safetyreportid))

    # Apply drug name filter if provided
    if filter_drug:
        q = (q.join(Drug, SafetyReport.safetyreportid == Drug.safetyreportid)
               .filter(Drug.medicinalproduct.ilike(f"%{filter_drug}%")))

    # Order results by received date in descending order
    q = q.order_by(SafetyReport.receivedate.desc())

    total_count = q.count()
    results = q.offset(offset_val).limit(per_page).all()

    # Prepare data rows for rendering
    rows = []
    for (sr, pt) in results:
        rows.append({
            'safetyreportid': sr.safetyreportid,
            'receivedate': sr.receivedate,
            'country': sr.primarysource_reportercountry,
            'age_group': pt.patientagegroup if pt else None,
            'sex': pt.patientsex if pt else None
        })

    # Calculate total number of pages
    total_pages = max(1, math.ceil(total_count / per_page))

    return render_template(
        'index.html',
        rows=rows,
        page=page,
        total_pages=total_pages,
        filter_drug=filter_drug
    )


@app.route('/report/<safetyreportid>')
def report_detail(safetyreportid):
    """
    Provides detailed information for a specific safety report.
    Includes patient demographics, reactions, and associated drugs.
    Groups drugs by medicinal product to consolidate entries.
    """
    # Retrieve the safety report along with related data
    report = (SafetyReport.query
              .options(joinedload(SafetyReport.patients))
              .options(joinedload(SafetyReport.drugs))
              .options(joinedload(SafetyReport.reactions))
              .options(joinedload(SafetyReport.company))
              .get_or_404(safetyreportid))

    # Organize drugs by medicinal product to avoid duplication
    drug_groups = {}
    for d in report.drugs:
        product_key = (d.medicinalproduct or 'Unknown').strip().lower()
        if product_key not in drug_groups:
            drug_groups[product_key] = {
                'medicinalproduct': d.medicinalproduct or 'Unknown',
                'count': 0,
                'records': []
            }
        drug_groups[product_key]['count'] += 1
        drug_groups[product_key]['records'].append(d)

    # Convert grouped drugs into a list for template rendering
    grouped_drugs = list(drug_groups.values())

    return render_template('report_detail.html',
                           report=report,
                           grouped_drugs=grouped_drugs)


@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    """
    Provides autocomplete suggestions for drug names based on user input.
    Returns a JSON list of matching medicinal products.
    """
    query = request.args.get('q', '').strip()
    suggestions = []
    if query:
        drug_q = (Drug.query
                  .filter(Drug.medicinalproduct.ilike(f"%{query}%"))
                  .with_entities(Drug.medicinalproduct)
                  .distinct()
                  .limit(10)
                 )
        results = drug_q.all()
        suggestions = [r[0] for r in results]
    return jsonify(suggestions)


@app.route('/search')
def search():
    """
    Handles search functionality for safety reports based on drug names.
    Supports pagination and indicates if more results are available.
    """
    query = request.args.get('query', '').strip()
    offset = int(request.args.get('offset', '0'))
    limit = 30
    has_more = False
    reports = []

    if query:
        q = (SafetyReport.query
             .join(Drug, SafetyReport.safetyreportid == Drug.safetyreportid)
             .filter(Drug.medicinalproduct.ilike(f"%{query}%"))
             .order_by(SafetyReport.transmissiondate.desc()))

        total_matched = q.count()
        has_more = (offset + limit) < total_matched

        reports = q.offset(offset).limit(limit).all()

    return render_template('search.html',
                           reports=reports,
                           query=query,
                           offset=offset,
                           limit=limit,
                           has_more=has_more)


@app.route('/statistics')
def statistics():
    """
    Displays statistical dashboards for a specified drug.
    Includes reports over time, age distribution, seriousness, country distribution, and top reactions.
    """
    drug_query = request.args.get('drug', '').strip()
    if not drug_query:
        # Render statistics page with no data if no drug is specified
        return render_template('statistics.html',
                               query=drug_query,
                               total_reports=0,
                               monthly_data={},
                               age_group_counts={},
                               seriousness_counts={},
                               serious_criteria_counts={},
                               country_counts={},
                               top_reactions={})

    # Filter safety reports related to the specified drug
    base_query = (SafetyReport.query
                  .join(Drug, SafetyReport.safetyreportid == Drug.safetyreportid)
                  .filter(Drug.medicinalproduct.ilike(f"%{drug_query}%")))

    total_reports = base_query.count()
    if total_reports == 0:
        # Render statistics page with no data if no reports are found
        return render_template('statistics.html',
                               query=drug_query,
                               total_reports=0,
                               monthly_data={},
                               age_group_counts={},
                               seriousness_counts={},
                               serious_criteria_counts={},
                               country_counts={},
                               top_reactions={})

    # Aggregate reports by year and month
    monthly_counts_query = (
        base_query.with_entities(
            extract('year', SafetyReport.receivedate).label('yr'),
            extract('month', SafetyReport.receivedate).label('mo'),
            func.count(SafetyReport.safetyreportid)
        )
        .group_by('yr', 'mo')
        .order_by('yr', 'mo')
        .all()
    )
    monthly_data = {}
    for (yr, mo, cnt) in monthly_counts_query:
        label = f"{int(yr)}-{int(mo):02d}"
        monthly_data[label] = int(cnt)

    # Define age group mappings
    age_map = {1: "Neonate", 2: "Infant", 3: "Child", 4: "Adolescent", 5: "Adult", 6: "Elderly"}

    # Aggregate patient age groups
    age_query = (
        base_query.join(Patient, SafetyReport.safetyreportid == Patient.safetyreportid)
        .with_entities(Patient.patientagegroup, func.count(Patient.id))
        .group_by(Patient.patientagegroup)
        .all()
    )
    age_group_counts = defaultdict(int)
    for (age_val, c_) in age_query:
        label = age_map.get(age_val, "Unknown")
        age_group_counts[label] += c_

    # Calculate counts for serious and non-serious reports
    serious_count = base_query.filter(SafetyReport.serious == 1).count()
    non_serious_count = base_query.filter(SafetyReport.serious != 1).count()
    seriousness_counts = {
        "Serious": serious_count,
        "Non-Serious": non_serious_count
    }

    # Aggregate counts for specific seriousness criteria
    serious_criteria_counts = {
        "Death": base_query.filter(SafetyReport.seriousnessdeath == 1).count(),
        "Life-Threatening": base_query.filter(SafetyReport.seriousnesslifethreatening == 1).count(),
        "Hospitalization": base_query.filter(SafetyReport.seriousnesshospitalization == 1).count(),
        "Disabling": base_query.filter(SafetyReport.seriousnessdisabling == 1).count(),
        "Congenital Anomaly": base_query.filter(SafetyReport.seriousnesscongenitalanomali == 1).count(),
        "Other": base_query.filter(SafetyReport.seriousnessother == 1).count()
    }

    # Aggregate reporter country distribution
    country_query = (
        base_query
        .with_entities(SafetyReport.primarysource_reportercountry, func.count(SafetyReport.safetyreportid))
        .group_by(SafetyReport.primarysource_reportercountry)
        .all()
    )
    country_counts = {}
    for (cc, ccount) in country_query:
        country_label = cc if cc else "Unknown"
        country_counts[country_label] = ccount

    # Identify top 5 reactions associated with the specified drug
    top_reactions_query = (
        Reaction.query
        .join(SafetyReport, Reaction.safetyreportid == SafetyReport.safetyreportid)
        .join(Drug, Reaction.safetyreportid == Drug.safetyreportid)
        .filter(Drug.medicinalproduct.ilike(f"%{drug_query}%"))
        .with_entities(Reaction.reactionmeddrapt, func.count(Reaction.id))
        .group_by(Reaction.reactionmeddrapt)
        .order_by(func.count(Reaction.id).desc())
        .limit(5)
        .all()
    )
    top_reactions = {r: int(c_) for (r, c_) in top_reactions_query}

    # Sort seriousness criteria in descending order of report counts
    serious_criteria_counts = sorted(serious_criteria_counts.items(), key=lambda x: x[1], reverse=True)
    serious_criteria_counts = dict(serious_criteria_counts)

    # Sort reporter country distribution in descending order of report counts
    country_counts = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)
    country_counts = dict(country_counts)

    # Sort top reactions in descending order of counts
    top_reactions = sorted(top_reactions.items(), key=lambda x: x[1], reverse=True)
    top_reactions = dict(top_reactions)

    return render_template('statistics.html',
                           query=drug_query,
                           total_reports=total_reports,
                           monthly_data=monthly_data,
                           age_group_counts=age_group_counts,
                           seriousness_counts=seriousness_counts,
                           serious_criteria_counts=serious_criteria_counts,
                           country_counts=country_counts,
                           top_reactions=top_reactions)


#########################
# ADMIN PANEL ROUTES
#########################

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    """
    Manages the admin panel functionality.
    Handles authentication and displays admin interface for data management.
    """
    if request.method == 'POST':
        # Process login attempt
        entered_pass = request.form.get('admin_password', '').strip()
        entered_hash = hashlib.sha256(entered_pass.encode()).hexdigest()

        if entered_hash == ADMIN_PW_HASH:
            # Successful authentication
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            # Failed authentication
            flash("Invalid password. Please try again.")
            return redirect(url_for('admin_panel'))

    # Check if user is authenticated
    if not session.get('admin_logged_in'):
        # Prompt for password if not authenticated
        return render_template('admin_login.html')

    # Retrieve table name and pagination parameters
    table_name = request.args.get('table', '').strip()
    start = int(request.args.get('start', '0'))
    rows = []
    columns = []
    if table_name:
        model = get_model_by_name(table_name)
        if not model:
            return render_template('admin.html',
                                   table_name=None,
                                   rows=[],
                                   columns=[],
                                   start=0)

        # Fetch column names for the selected table
        columns = get_model_columns(model)

        # Query the selected table with pagination
        q = db.session.query(model)
        data_objs = q.offset(start).limit(100).all()

        # Convert database objects to dictionaries for template rendering
        rows = []
        for obj in data_objs:
            row_dict = {}
            primary_key = get_primary_key_value(obj)
            row_dict['id_key'] = primary_key

            for col in columns:
                val = getattr(obj, col, None)
                if isinstance(val, datetime.date):
                    val = val.isoformat()
                elif val is None:
                    val = None
                row_dict[col] = val
            rows.append(row_dict)

    return render_template('admin.html',
                           table_name=table_name,
                           columns=columns,
                           rows=rows,
                           start=start)


@app.route('/admin/logout')
def admin_logout():
    """
    Logs out the admin user by clearing the session.
    Redirects to the home page after logout.
    """
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))


@app.errorhandler(404)
def page_not_found(e):
    """
    Renders a custom 404 error page for undefined routes.
    """
    return render_template('404.html'), 404


@app.route('/admin/edit/<table_name>/<row_id>')
def admin_edit_row(table_name, row_id):
    """
    Provides a form for editing a specific row in the admin panel.
    Retrieves current values to populate the form fields.
    """
    model = get_model_by_name(table_name)
    if not model:
        return "<p class='text-red-500'>Invalid table.</p>"

    # Retrieve the specific record based on primary key
    obj = db.session.query(model).get(row_id)
    if not obj:
        return "<p class='text-red-500'>Row not found.</p>"

    # Gather current column values for the form
    columns = get_model_columns(model)
    col_values = {}
    for col in columns:
        val = getattr(obj, col, None)
        if isinstance(val, datetime.date):
            val = val.isoformat()
        col_values[col] = val

    # Render the edit form with current values
    return render_template('admin_edit_form.html',
                           table_name=table_name,
                           row_id=row_id,
                           columns=columns,
                           col_values=col_values)


@app.route('/admin/update', methods=['POST'])
def admin_update():
    """
    Processes updates to a specific row in the admin panel.
    Validates and converts form data before committing changes to the database.
    Returns a JSON response indicating success or failure.
    """
    table_name = request.form.get('table', '').strip()
    row_id = request.form.get('row_id', '').strip()

    model = get_model_by_name(table_name)
    if not model:
        return jsonify({"success": False, "error": "Invalid table."})

    obj = db.session.query(model).get(row_id)
    if not obj:
        return jsonify({"success": False, "error": "Row not found."})

    columns = get_model_columns(model)
    # Update each column with form data if present
    for col in columns:
        form_key = f"col_{col}"
        if form_key in request.form:
            raw_val = request.form[form_key]
            # Convert the raw form value to the appropriate data type
            converted_val = convert_value_for_column(type(getattr(obj, col)), raw_val)
            setattr(obj, col, converted_val)

    # Attempt to commit changes to the database
    try:
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


#########################
# HELPER FUNCTIONS
#########################

def get_model_by_name(table_name):
    """
    Maps a table name string to its corresponding SQLAlchemy model class.
    Returns the model class if found, else None.
    """
    mapping = {
        'safety_reports': SafetyReport,
        'patients': Patient,
        'reactions': Reaction,
        'drugs': Drug,
        'companies': Company
    }
    return mapping.get(table_name, None)


def get_model_columns(model_class):
    """
    Retrieves a list of column names for the given SQLAlchemy model.
    Excludes relationship-only attributes.
    """
    insp = db.inspect(model_class)
    columns = [c.key for c in insp.columns]
    return columns


def get_primary_key_value(obj):
    """
    Retrieves the primary key value of a SQLAlchemy model instance.
    Supports single and composite primary keys.
    """
    insp = db.inspect(obj)
    pks = insp.identity
    if len(pks) == 1:
        return pks[0]
    else:
        return "_".join(str(x) for x in pks)


def convert_value_for_column(current_type, raw_val):
    """
    Converts raw form input into the appropriate data type based on the column's type.
    Handles boolean, integer, date, and string types.
    """
    if raw_val == '':
        return None

    if current_type == bool:
        return raw_val.lower() in ['true', '1', 'yes', 'on']
    if current_type == int:
        try:
            return int(raw_val)
        except:
            return None
    if current_type == datetime.date:
        try:
            return datetime.date.fromisoformat(raw_val)
        except:
            return None
    if current_type == type(None):
        try:
            return int(raw_val)
        except:
            pass
        if raw_val.lower() in ['true', 'false', 'yes', 'no', '1', '0']:
            return raw_val.lower() in ['true', '1', 'yes']
        try:
            return datetime.date.fromisoformat(raw_val)
        except:
            pass
        return raw_val

    return raw_val


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)
