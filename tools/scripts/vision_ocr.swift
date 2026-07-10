import AppKit
import Foundation
import Vision

if CommandLine.arguments.count < 2 {
    fputs("usage: vision_ocr.swift <image>\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let image = NSImage(contentsOf: imageURL) else {
    fputs("failed to load image\n", stderr)
    exit(1)
}

var rect = CGRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    fputs("failed to create CGImage\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("vision request failed: \(error)\n", stderr)
    exit(1)
}

let lines = (request.results ?? []).compactMap { observation -> String? in
    observation.topCandidates(1).first?.string
}
print(lines.joined(separator: "\n"))
