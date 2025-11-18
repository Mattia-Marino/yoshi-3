package logger

import (
	"io"
	"os"
	"strings"

	"github.com/sirupsen/logrus"
	"gopkg.in/natefinch/lumberjack.v2"
)

// Init creates a logger that writes to stdout and a rotating file.
// logPath: path to the log file (e.g. "./users.log")
// level: "debug", "info", "warn", "error"
func Init(logPath, level string) *logrus.Logger {
	l := logrus.New()
	l.SetFormatter(&logrus.TextFormatter{
		FullTimestamp: true,
	})

	lvl, err := logrus.ParseLevel(strings.ToLower(level))
	if err != nil {
		lvl = logrus.InfoLevel
	}
	l.SetLevel(lvl)

	if logPath == "" {
		logPath = "./users.log"
	}

	rotator := &lumberjack.Logger{
		Filename:   logPath,
		MaxSize:    10, // megabytes
		MaxBackups: 5,
		MaxAge:     28,   // days
		Compress:   true, // compress rotated files
	}

	// write to both stdout and file
	l.SetOutput(io.MultiWriter(os.Stdout, rotator))

	return l
}
