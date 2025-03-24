# models.py

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class SafetyReport(db.Model):
    """
    Represents an adverse event safety report.
    Captures key details about the event, its seriousness, associated drugs, patients, reactions, and the reporting company.
    """
    __tablename__ = 'safety_reports'

    safetyreportid = db.Column(db.String(50), primary_key=True)
    serious = db.Column(db.SmallInteger, nullable=False)
    seriousnessdeath = db.Column(db.SmallInteger, default=None)
    seriousnesslifethreatening = db.Column(db.SmallInteger, default=None)
    seriousnesshospitalization = db.Column(db.SmallInteger, default=None)
    seriousnessdisabling = db.Column(db.SmallInteger, default=None)
    seriousnesscongenitalanomali = db.Column(db.SmallInteger, default=None)
    seriousnessother = db.Column(db.SmallInteger, default=None)
    receivedate = db.Column(db.Date, nullable=False)
    receiptdate = db.Column(db.Date, nullable=False)
    primarysource_reportercountry = db.Column(db.String(2), nullable=True)
    companynumb = db.Column(db.String(100), db.ForeignKey('companies.companynumb'), nullable=True)

    # Establish relationships with other models
    patients = db.relationship('Patient', backref='safety_report', lazy='select', cascade="all, delete-orphan")
    drugs = db.relationship('Drug', backref='safety_report', lazy='select', cascade="all, delete-orphan")
    reactions = db.relationship('Reaction', backref='safety_report', lazy='select', cascade="all, delete-orphan")
    company = db.relationship('Company', backref='safety_reports', lazy='select')

    def __repr__(self):
        """
        Returns a string representation of the SafetyReport instance.
        """
        return f"<SafetyReport {self.safetyreportid}>"


class Patient(db.Model):
    """
    Represents a patient involved in a safety report.
    Stores demographic information such as age group and sex.
    """
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    safetyreportid = db.Column(db.String(50), db.ForeignKey('safety_reports.safetyreportid'), nullable=True)
    patientagegroup = db.Column(db.SmallInteger, nullable=True)
    patientsex = db.Column(db.SmallInteger, nullable=True)

    def __repr__(self):
        """
        Returns a string representation of the Patient instance.
        """
        return f"<Patient {self.id} for {self.safetyreportid}>"


class Reaction(db.Model):
    """
    Represents an adverse reaction associated with a safety report.
    Details the specific clinical signs or symptoms experienced.
    """
    __tablename__ = 'reactions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    safetyreportid = db.Column(db.String(50), db.ForeignKey('safety_reports.safetyreportid'), nullable=True)
    reactionmeddrapt = db.Column(db.String(255), nullable=False)
    reactionoutcome = db.Column(db.SmallInteger, nullable=True)

    def __repr__(self):
        """
        Returns a string representation of the Reaction instance.
        """
        return f"<Reaction {self.reactionmeddrapt} for {self.safetyreportid}>"


class Drug(db.Model):
    """
    Represents a drug involved in a safety report.
    Captures details about the drug's role, dosage, administration, and active substances.
    """
    __tablename__ = 'drugs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    safetyreportid = db.Column(db.String(50), db.ForeignKey('safety_reports.safetyreportid'), nullable=True)
    drugcharacterization = db.Column(db.SmallInteger, nullable=False)
    medicinalproduct = db.Column(db.String(255), nullable=False)
    drugstructuredosagenumb = db.Column(db.Integer, nullable=True)
    drugstructuredosageunit = db.Column(db.String(10), nullable=True)
    drugdosagetext = db.Column(db.String(255), nullable=True)
    drugdosageform = db.Column(db.String(100), nullable=True)
    drugadministrationroute = db.Column(db.String(10), nullable=True)
    drugindication = db.Column(db.String(255), nullable=True)
    actiondrug = db.Column(db.SmallInteger, nullable=True)
    drugrecurreadministration = db.Column(db.SmallInteger, nullable=True)
    drugadditional = db.Column(db.SmallInteger, nullable=True)
    activesubstancename = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        """
        Returns a string representation of the Drug instance.
        """
        return f"<Drug {self.medicinalproduct} for {self.safetyreportid}>"


class Company(db.Model):
    """
    Represents a company associated with safety reports.
    Stores the company's unique identifier and official name.
    """
    __tablename__ = 'companies'

    companynumb = db.Column(db.String(100), primary_key=True)
    companyname = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        """
        Returns a string representation of the Company instance.
        """
        return f"<Company {self.companynumb} - {self.companyname}>"
