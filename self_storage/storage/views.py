from django.shortcuts import render

def index(request):
    return render(request, "storage/index.html")

def faq(request):
    return render(request, "storage/faq.html")

def boxes(request):
    return render(request, "storage/boxes.html")

def my_rent(request):
    return render(request, "storage/my-rent.html")
