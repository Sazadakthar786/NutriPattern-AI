# Doctor Portal Guide - NutriPattern AI

## Overview
The Doctor Portal is a professional interface that allows doctors to review patient medical reports, add medical comments, and provide expert guidance. It's designed to be visually distinct from the user dashboard with a modern, medical-focused UI.

## Features

### 🏥 **Professional Dashboard**
- Clean, medical-themed interface
- Patient report overview with status indicators
- Real-time statistics (total reports, commented reports)
- Responsive design for all devices

### 📋 **Patient Report Management**
- **Report Cards**: Each patient report displayed in an organized card format
- **Status Tracking**: Visual indicators for reviewed vs. pending reports
- **Medical Parameters**: Extracted values displayed in an easy-to-read grid
- **Condition Tags**: Detected health conditions highlighted with color-coded tags
- **File Information**: Report filename, upload date, and patient details

### 💬 **Comment System**
- **Add Comments**: Doctors can add medical assessments and recommendations
- **Edit Comments**: Update existing comments as needed
- **Timestamp Tracking**: Automatic recording of when comments were added
- **Rich Text Support**: Multi-line textarea for detailed medical notes

### 🔍 **Enhanced Viewing**
- **Full Report Modal**: Click to view complete report details
- **Parameter Analysis**: Organized display of all extracted medical values
- **Condition Overview**: Clear presentation of detected health issues
- **Patient Context**: Username and report history for each patient

## How to Access

### For Doctors (Users with role='doctor')
1. Log in with your doctor account
2. Click "Doctor Portal" in the sidebar
3. You'll see all shared patient reports

### For Demo Users (Regular users)
1. Log in with any account
2. Click "Demo Doctor View" in the sidebar
3. You can view and comment on reports (demo mode)

## Setup Instructions

### 1. Create a Doctor Account
```bash
# Register a new user and select 'doctor' role
# Or update existing user in database:
UPDATE user SET role = 'doctor' WHERE username = 'your_username';
```

### 2. Share Patient Reports
- Patients must check "Share with Doctor" when uploading reports
- Only shared reports appear in the doctor portal

### 3. Database Schema
The system automatically adds a `comment_timestamp` field to track when comments were added.

## Usage Examples

### Adding a Medical Comment
1. Navigate to a patient report
2. Click "Add Comment" button
3. Write your medical assessment
4. Click "Save Comment"

### Reviewing Patient Data
1. View extracted medical parameters
2. Check detected health conditions
3. Review previous comments
4. Add new recommendations

### Managing Multiple Patients
- Use the grid layout to compare multiple reports
- Filter by status (reviewed/pending)
- Track comment history per patient

## Technical Details

### Backend Routes
- `GET /doctor` - Doctor dashboard view
- `POST /doctor/comment/<report_id>` - Add/edit comments

### Database Models
- `HealthReport`: Stores medical reports and doctor comments
- `User`: User accounts with role-based access
- `comment_timestamp`: Tracks when comments were added

### Security Features
- Login required for all doctor portal access
- Role-based access control (configurable)
- User-specific data isolation

## Testing the Portal

### 1. Upload a Medical Report
- Go to your dashboard
- Upload a medical report (PDF/image)
- Check "Share with Doctor"
- Submit the form

### 2. Access Doctor Portal
- Click "Demo Doctor View" in sidebar
- You should see your uploaded report
- Try adding a comment

### 3. Test Features
- Add/edit comments
- View report details
- Check responsive design on mobile

## Customization

### Styling
- All styles are in `static/style.css`
- Doctor-specific styles start at line 788
- Easy to modify colors, layouts, and themes

### Functionality
- Add new report fields in the model
- Extend comment system with attachments
- Integrate with external medical databases

## Troubleshooting

### Common Issues
1. **No reports visible**: Check if reports are shared with doctors
2. **Can't add comments**: Verify user authentication and permissions
3. **Styling issues**: Clear browser cache and check CSS file

### Database Issues
- Delete `healthapp.db` to reset database
- Restart Flask application
- Check console for error messages

## Future Enhancements

### Planned Features
- **Patient Communication**: Direct messaging system
- **Report Templates**: Standardized medical report formats
- **Analytics Dashboard**: Patient trend analysis
- **Integration**: Connect with hospital systems
- **Notifications**: Alert system for new reports

### API Extensions
- RESTful API for mobile apps
- Webhook support for external systems
- Real-time updates via WebSockets

## Support

For technical support or feature requests:
- Check the main project documentation
- Review Flask application logs
- Test with sample medical reports

---

**Note**: This is a demonstration system. In production, implement proper medical data security, HIPAA compliance, and user authentication.
