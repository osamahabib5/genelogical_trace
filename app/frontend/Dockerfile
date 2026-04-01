# Step 1: Build the React application
FROM node:18-alpine AS build

WORKDIR /app

COPY package.json ./
RUN npm install

# --- CRITICAL SECTION: Accept Build Args ---
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL

COPY . .

# Create the production build
RUN npm run build

# Step 2: Serve the app using a lightweight server (Nginx)
FROM nginx:stable-alpine

# Copy the build output from the first step to Nginx's html folder
COPY --from=build /app/build /usr/share/nginx/html

# Expose port 80 (Standard for Azure Container Apps)
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]