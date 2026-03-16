FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY server.go ./
RUN go build -o /gui-server .

FROM alpine:3.19
WORKDIR /app
COPY --from=build /gui-server .
COPY css/ css/
COPY html/ html/
COPY javascript/ javascript/
ENV STATIC_DIR=/app
EXPOSE 8080
CMD ["./gui-server"]
