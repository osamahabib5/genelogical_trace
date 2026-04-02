# Step 1: Build the React application
FROM node:18-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

# --- BUILD SECTION ---
# Note: Since we are now using the Nginx Proxy approach with relative paths ('/api'), 
# we don't strictly need REACT_APP_API_URL at build time anymore, 
# but keeping it for backward compatibility doesn't hurt.
ARG REACT_APP_API_URL=/api
ENV REACT_APP_API_URL=$REACT_APP_API_URL

COPY . .

# Create the production build
RUN npm run build

# Step 2: Serve the app using a lightweight server (Nginx)
FROM nginx:stable-alpine

# --- CRITICAL CHANGE ---
# Instead of copying directly to conf.d, we copy to the templates folder.
# Nginx's entrypoint script will run 'envsubst' on this file and 
# output the result to /etc/nginx/conf.d/default.conf automatically.
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy the build output from the first step to Nginx's html folder
COPY --from=build /app/build /usr/share/nginx/html

# Expose port 80 (Standard for Azure Container Apps)
EXPOSE 80

# The default Nginx entrypoint handles the variable substitution
CMD ["nginx", "-g", "daemon off;"]