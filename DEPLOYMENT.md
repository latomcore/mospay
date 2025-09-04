# MosPay Deployment Guide for Render.com

## Prerequisites

1. **GitHub Repository**: Your code should be pushed to `https://github.com/latomcore/mospay.git`
2. **Render Account**: Sign up at [render.com](https://render.com)

## Deployment Steps

### 1. Create a New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository: `https://github.com/latomcore/mospay.git`
4. Configure the service:
   - **Name**: `mospay`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free (or upgrade as needed)

### 2. Create a PostgreSQL Database

1. In Render Dashboard, click "New +" → "PostgreSQL"
2. Configure the database:
   - **Name**: `mospay-db`
   - **Database**: `mospay`
   - **User**: `mospay_user`
   - **Plan**: Free (or upgrade as needed)

### 3. Configure Environment Variables

In your web service settings, add these environment variables:

```
FLASK_ENV=production
SECRET_KEY=<generate-a-secure-secret-key>
JWT_SECRET_KEY=<generate-a-secure-jwt-secret>
DATABASE_URL=<copy-from-postgres-database-connection-string>
```

**To generate secure keys:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Deploy

1. Click "Create Web Service"
2. Render will automatically:
   - Clone your repository
   - Install dependencies
   - Build the application
   - Deploy to a public URL

### 5. Access Your Application

After deployment, you'll get a URL like: `https://mospay.onrender.com`

**Available endpoints:**
- **Admin Portal**: `https://mospay.onrender.com/admin`
- **API Documentation**: `https://mospay.onrender.com/docs`
- **API Base**: `https://mospay.onrender.com/api/v1`
- **Health Check**: `https://mospay.onrender.com/health`

### 6. Default Credentials

The application creates a default super admin user:
- **Username**: `admin`
- **Password**: `admin123`
- **Email**: `admin@mospay.com`

**⚠️ Important**: Change these credentials immediately after first login!

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `FLASK_ENV` | Flask environment (production) | Yes |
| `SECRET_KEY` | Flask secret key for sessions | Yes |
| `JWT_SECRET_KEY` | JWT token signing key | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |

## Troubleshooting

### Common Issues

1. **Build Fails**: Check that all dependencies are in `requirements.txt`
2. **Database Connection Error**: Verify `DATABASE_URL` is correct
3. **Application Crashes**: Check logs in Render dashboard
4. **Static Files Not Loading**: Ensure static files are committed to git

### Logs

View application logs in the Render dashboard under your service's "Logs" tab.

### Health Check

The application includes a health check endpoint at `/health` that verifies:
- Application is running
- Database connection is working
- Service status

## Security Considerations

1. **Change Default Credentials**: Update admin username/password
2. **Use Strong Secrets**: Generate secure SECRET_KEY and JWT_SECRET_KEY
3. **HTTPS**: Render provides HTTPS by default
4. **Environment Variables**: Never commit secrets to git

## Scaling

- **Free Plan**: Limited to 750 hours/month
- **Starter Plan**: $7/month for always-on service
- **Professional Plan**: $25/month for better performance

## Support

For deployment issues:
1. Check Render documentation: [docs.render.com](https://docs.render.com)
2. Review application logs
3. Verify environment variables
4. Test locally first

## Post-Deployment Checklist

- [ ] Application is accessible via public URL
- [ ] Admin portal login works
- [ ] Database connection is established
- [ ] API endpoints respond correctly
- [ ] Documentation page loads
- [ ] Default admin credentials changed
- [ ] Health check passes
- [ ] SSL certificate is active (HTTPS)

